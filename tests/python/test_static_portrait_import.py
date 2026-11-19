"""Neutral synthetic fixtures: no game art or real design approval records."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from tools.art import design, png
from tools.art.manifest import ArtError, canonical, digest, read_json
from tools.art.portraits import static_import as handoff


class StaticPortraitImportTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.inputs, self.trust, self.pending = [self.root / d for d in ('source', 'trust', 'pending')]
        for p in (self.inputs, self.trust, self.pending):
            p.mkdir()
        self.concept = self.inputs / 'concept.json'
        self.sheet = self.inputs / 'design.json'
        self.portrait = self.inputs / 'source.png'
        self.request = self.inputs / 'request.json'
        self.identity = {'character_id': 'sample_marker', 'concept_revision': 'c-1', 'design_revision': 'd-1'}
        (self.inputs / 'concept.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
        (self.inputs / 'design.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"><circle r="2"/></svg>')
        self.portrait.write_bytes(png.encode(2, 1, b'\0\0\0\0\xff\0\0\xff'))
        self.write(self.concept, self.record('concept', 'c-1', []))
        self.write(self.sheet, self.record('design', 'd-1', [
            self.reference('concept.json', 'upstream_record'), self.reference('concept.svg', 'concept_image')]))

    def write(self, path, value):
        path.write_bytes(canonical(value))

    def reference(self, name, role=None):
        item = {'path': name, 'sha256': digest(self.inputs / name)}
        if role:
            item['role'] = role
        return item

    def record(self, stage, rev, refs):
        return {'schema_version': 1, 'kind': 'character_design',
                'character': {'id': 'sample_marker', 'revision': rev}, 'stage': stage,
                'references': refs, 'producer': {'name': 'neutral-fixture', 'version': 'one'},
                'output': self.reference(stage + '.svg'),
                'limitations': ['Synthetic geometry only. Not game artwork.'],
                'review': {'status': 'pending', 'reviewer': None, 'notes': 'Fixture pending.', 'basis_sha256': None}}

    def mark_design_accepted_in_fixture(self):
        record = read_json(self.sheet)
        basis = design.review_basis(record)
        record['review'] = {'status': 'accepted', 'reviewer': 'synthetic-test-reviewer',
                            'notes': 'Synthetic positive fixture, not human approval.', 'basis_sha256': basis}
        self.write(self.sheet, record)
        return basis

    def mock_receipt(self, basis):
        receipt = self.trust / (digest(self.sheet) + '.json')
        self.write(receipt, {'schema_version': 1, 'kind': 'trusted_design_approval', 'decision': 'accepted',
                             'intent': handoff.INTENT, 'character_id': 'sample_marker', 'revision': 'd-1',
                             'design_record_sha256': digest(self.sheet), 'review_basis_sha256': basis,
                             'reviewer': 'synthetic-test-reviewer'})
        return receipt

    def export(self):
        return handoff.export_request(self.concept, self.sheet, self.portrait, self.request, **self.identity)

    def consume(self, trust=None):
        return handoff.import_existing(self.concept, self.sheet, self.portrait, self.request,
                                       trust or self.trust, self.pending, **self.identity)

    def fixture(self):
        receipt = self.mock_receipt(self.mark_design_accepted_in_fixture())
        request = self.export()
        return receipt, request

    def assertBlocked(self, pattern, callable=None):
        with self.assertRaisesRegex(ArtError, pattern):
            (callable or self.consume)()
        self.assertEqual(list(self.pending.iterdir()), [])

    def test_fixture_bundle_exact_bytes_and_explicitly_pending(self):
        receipt, request = self.fixture()
        self.assertEqual(request['lineage']['concept']['record_sha256'], digest(self.concept))
        self.assertEqual(request['lineage']['design']['record_sha256'], digest(self.sheet))
        report = self.consume()
        target = self.pending / report['bundle']
        self.assertEqual(report['trusted_design_receipt_sha256'], digest(receipt))
        self.assertEqual(report['request_sha256'], digest(self.request))
        with ZipFile(target) as bundle:
            self.assertEqual(bundle.namelist(), ['portrait.png', 'request.json', 'candidate.json'])
            self.assertEqual(bundle.read('portrait.png'), self.portrait.read_bytes())
            self.assertEqual(bundle.read('request.json'), self.request.read_bytes())
            self.assertEqual(bundle.read('candidate.json'),
                             canonical({k:v for k,v in report.items() if k != 'bundle'}))
        self.assertEqual(report['review_status'], 'pending')
        self.assertFalse(any(report[k] for k in ('generated', 'final_art_approved', 'runtime_integrated')))
        old_bytes = target.read_bytes()
        with self.assertRaisesRegex(ArtError, 'already exists'):
            self.consume()
        self.assertEqual(target.read_bytes(), old_bytes)
        with self.assertRaisesRegex(ArtError, 'already exists'):
            self.export()
        self.assertEqual(read_json(self.request), request)

    def test_pending_stops_even_with_synthetic_entry(self):
        self.mock_receipt(design.review_basis(read_json(self.sheet)))
        self.export()
        self.assertBlocked('design is not accepted')

    def test_declared_accepted_and_recomputed_hash_are_insufficient(self):
        self.mark_design_accepted_in_fixture()
        self.export()
        self.assertBlocked('trusted approval receipt missing')

    def test_receipt_intent_or_reviewer_cannot_change(self):
        receipt, _ = self.fixture()
        original = read_json(receipt)
        for field, altered in [('intent', 'promote_to_release'), ('reviewer', 'other'),
                               ('character_id', 'sample_other'), ('revision', 'd-2')]:
            with self.subTest(field=field):
                self.write(receipt, {**original, field: altered})
                self.assertBlocked('receipt scope, revision, reviewer or binding mismatch')

    def test_receipt_bool_not_schema_version(self):
        receipt, _ = self.fixture()
        value = read_json(receipt)
        self.write(receipt, {**value, 'schema_version': True})
        self.assertBlocked('receipt scope, revision, reviewer or binding mismatch')

    def test_untrusted_colocated_receipt_is_not_allowed(self):
        receipt, _ = self.fixture()
        self.write(self.inputs / receipt.name, read_json(receipt))
        self.assertBlocked('approval store must be separate', lambda: self.consume(self.inputs))

    def test_no_approval_receipt_symlink(self):
        receipt, _ = self.fixture()
        outside = self.inputs / receipt.name
        receipt.rename(outside)
        try:
            receipt.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest('symlinks not supported')
        self.assertBlocked('trusted approval receipt missing')

    def test_stale_references_are_revalidated(self):
        self.fixture()
        (self.inputs / 'concept.svg').write_text('changed')
        self.assertBlocked('source SHA-256 mismatch')

    def test_locally_rehashed_design_cannot_reuse_a_prior_receipt(self):
        self.fixture()
        record = read_json(self.sheet)
        (self.inputs / 'design.svg').write_text('<svg><rect width="1" height="1"/></svg>')
        record['output'] = self.reference('design.svg')
        record['review']['basis_sha256'] = design.review_basis(record)
        self.write(self.sheet, record)
        self.request.unlink()
        self.export()  # Local lineage is now consistent, but not re-approved.
        self.assertBlocked('trusted approval receipt missing')

    def test_cannot_stage_inside_a_game_project(self):
        self.fixture()
        (self.pending / 'project.godot').write_text('; fixture')
        with self.assertRaisesRegex(ArtError, 'outside Godot project roots'):
            self.consume()
        self.assertEqual([e.name for e in self.pending.iterdir()], ['project.godot'])

    def test_rev_mismatch_fails(self):
        self.fixture()
        self.identity['design_revision'] = 'd-stale'
        self.assertBlocked('identity/revision does not match')

    def test_design_links_to_the_exact_selected_concept(self):
        original = self.concept.with_name('other.json')
        original.write_bytes(self.concept.read_bytes())
        record = read_json(self.sheet)
        record['references'][0] = self.reference('other.json', 'upstream_record')
        self.write(self.sheet, record)
        self.assertBlocked('design does not reference the exact selected concept', self.export)

    def test_portrait_replacement_makes_export_stale(self):
        self.fixture()
        self.portrait.write_bytes(png.encode(2, 1, b'\0\0\0\0\0\xff\0\xff'))
        self.assertBlocked('stale or invalid import request')

    def test_bad_png_even_if_a_request_pins_it(self):
        self.portrait.write_bytes(b'not a PNG')
        self.fixture()
        self.assertBlocked('invalid or oversized PNG')

    def test_final_validation_failure_leaves_no_bundle(self):
        self.fixture()
        verify = handoff._approval
        def check_then_remove(*args):
            digest_found = verify(*args)
            receipt = self.trust / (digest(self.sheet) + '.json')
            receipt.unlink()
            return digest_found
        with patch.object(handoff, '_approval', side_effect=check_then_remove):
            self.assertBlocked('trusted approval receipt missing')

    def test_publish_collision_during_atomic_commit_is_non_overwriting(self):
        self.fixture()
        def competing_link(src, target):
            target.write_bytes(b'competing caller data')
            raise FileExistsError('exists')
        with patch.object(handoff.os, 'link', side_effect=competing_link):
            with self.assertRaises(FileExistsError):
                self.consume()
        entries = list(self.pending.iterdir())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].read_bytes(), b'competing caller data')

    def test_cli_pending_fixture_status(self):
        command = [sys.executable, '-m', 'tools.art.portraits.static_import']
        flags = ['--concept', str(self.concept), '--design', str(self.sheet), '--portrait', str(self.portrait),
                 '--character-id', 'sample_marker', '--concept-revision', 'c-1', '--design-revision', 'd-1']
        made = subprocess.run(command + ['export-request', *flags, '--output', str(self.request)],
                              check=True, capture_output=True)
        self.assertIn(b'static_portrait_import_request', made.stdout)
        attempted = subprocess.run(command + ['import-existing', *flags, '--request', str(self.request),
                                               '--trusted-approval-directory', str(self.trust),
                                               '--pending-directory', str(self.pending)], capture_output=True)
        self.assertEqual(attempted.returncode, 1)
        self.assertIn(b'design is not accepted', attempted.stderr)
        self.assertEqual(list(self.pending.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
