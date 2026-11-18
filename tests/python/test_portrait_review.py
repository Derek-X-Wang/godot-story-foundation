import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib
from tools.art.portraits.review import build


def png():
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 2, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress((b'\0' + b'\x99\x88\x77\xff' * 2) * 2)) + chunk(b'IEND', b''))


class PortraitReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.sources = self.root / 'sources'
        self.sources.mkdir()
        self.data = png()
        (self.sources / 'neutral.png').write_bytes(self.data)
        self.record = dict(name='neutral', source_sha256=hashlib.sha256(self.data).hexdigest(),
                           source_size=[2, 2], projection_depth='unobservable', automatic_anatomy_verdict=None,
                           status='localized_review_candidates', pose_gate='unknown', semantic_gate='abstain',
                           regions=[dict(kind='review', reason='unknown occluder', action='inspect',
                                         bbox_normalized_xyxy=[0, 0, .5, 1])])
        self.packet = dict(schema='portrait-local-review-v1', mode='review_only',
                           automatic_approval=False, records=[self.record])

    def run_build(self, output='out'):
        file = self.root / 'packet.json'
        file.write_text(json.dumps(self.packet))
        return build(file, self.sources, self.root / output)

    def fails(self):
        with self.assertRaises((ValueError, OSError)):
            self.run_build()
        self.assertFalse((self.root / 'out').exists())

    def test_standalone_offline_build(self):
        summary = self.run_build()
        self.assertFalse(summary['automatic_approval'])
        doc = (self.root / 'out/report.html').read_text()
        self.assertIn('data:image/png;base64,', doc)
        self.assertIn("default-src 'none'", doc)
        self.assertNotIn('<script', doc)
        self.assertEqual((self.sources / 'neutral.png').read_bytes(), self.data)

    def test_abstention_is_successful_report_not_failed_art(self):
        self.record.update(status='abstain_pose', regions=[])
        self.assertEqual(self.run_build()['records'][0]['region_count'], 0)

    def test_different_provider_extra_evidence_is_optional(self):
        self.record['provider_extension'] = {'any': 'ignored'}
        self.run_build()

    def test_existing_output_not_replaced(self):
        self.run_build()
        before = (self.root / 'out/report.html').read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_build()
        self.assertEqual(before, (self.root / 'out/report.html').read_bytes())

    def test_changed_source_rejected(self):
        (self.sources / 'neutral.png').write_bytes(self.data + b'x')
        self.fails()

    def test_source_dimensions_rejected(self):
        self.record['source_size'] = [3, 2]
        self.fails()

    def test_missing_source_rejected(self):
        (self.sources / 'neutral.png').unlink()
        self.fails()

    def test_traversal_name_rejected(self):
        self.record['name'] = '../neutral'
        self.fails()

    def test_outside_symlink_rejected(self):
        target = self.root / 'other.png'
        target.write_bytes(self.data)
        (self.sources / 'neutral.png').unlink()
        (self.sources / 'neutral.png').symlink_to(target)
        self.fails()

    def test_automatic_approval_rejected(self):
        self.packet['automatic_approval'] = True
        self.fails()

    def test_anatomy_verdict_rejected(self):
        self.record['automatic_anatomy_verdict'] = 'pass'
        self.fails()

    def test_missing_null_verdict_rejected(self):
        del self.record['automatic_anatomy_verdict']
        self.fails()

    def test_inferred_depth_rejected(self):
        self.record['projection_depth'] = 'known'
        self.fails()

    def test_bad_boxes_rejected(self):
        for box in ([0, 0, float('nan'), 1], [0, 0, 2, 1], [.5, 0, .2, 1], [False, 0, 1, 1]):
            with self.subTest(box=box):
                self.record['regions'][0]['bbox_normalized_xyxy'] = box
                self.fails()

    def test_duplicate_names_rejected(self):
        self.packet['records'].append(copy.deepcopy(self.record))
        self.fails()

    def test_html_escaped(self):
        self.record['regions'][0]['reason'] = '<img src=https://invalid.test onerror=alert(1)>'
        self.run_build()
        doc = (self.root / 'out/report.html').read_text()
        self.assertIn('&lt;img src=', doc)
        self.assertNotIn('<img src=https:', doc)

    def test_truncated_png_rejected_even_with_matching_hash(self):
        data = self.data[:33]
        (self.sources / 'neutral.png').write_bytes(data)
        self.record['source_sha256'] = hashlib.sha256(data).hexdigest()
        self.fails()

    def test_corrupt_png_rejected_even_with_matching_hash(self):
        data = bytearray(self.data)
        data[-1] ^= 1
        (self.sources / 'neutral.png').write_bytes(data)
        self.record['source_sha256'] = hashlib.sha256(data).hexdigest()
        self.fails()

    def test_cumulative_pixel_budget(self):
        for i in range(2):
            r = copy.deepcopy(self.record)
            r['name'] = 'neutral' + str(i)
            (self.sources / (r['name'] + '.png')).write_bytes(self.data)
            self.packet['records'].append(r)
        with patch('tools.art.portraits.review.MAX_TOTAL_PIXELS', 8):
            self.fails()

    def test_deterministic_output(self):
        self.run_build('one')
        self.run_build('two')
        for name in ('report.html', 'review-build.json'):
            self.assertEqual((self.root / 'one' / name).read_bytes(), (self.root / 'two' / name).read_bytes())


if __name__ == '__main__':
    unittest.main()
