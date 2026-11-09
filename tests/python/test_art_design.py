from __future__ import annotations
import copy
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.art.design import check, review_basis, validate_record
from tools.art.manifest import ArtError, canonical, digest, read_json


class DesignProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / 'examples/art/design', self.root / 'design')
        self.path = self.root / 'design/record.json'
        self.record = read_json(self.path)

    def write(self):
        self.path.write_bytes(canonical(self.record))

    def check(self, **kwargs):
        return check(self.path, character_id='sample_marker', revision='draft-1', **kwargs)

    def test_valid_record_is_read_only_and_makes_bounded_claims(self):
        before = {p.name: p.read_bytes() for p in self.path.parent.iterdir()}
        report = self.check()
        self.assertTrue(report['local_file_hashes_match'])
        self.assertFalse(report['record_matches_independent_expectation'])
        self.assertEqual(report['declared_human_review_status'], 'pending')
        for field in ('art_approval', 'integration_approval'):
            self.assertEqual(report[field], 'not_determined_by_tool')
        for field in ('semantic_correctness', 'remote_persistence'):
            self.assertEqual(report[field], 'not_verified')
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.path.parent.iterdir()})

    def test_caller_identity_and_revision_are_independent(self):
        for key, value in [('id', 'different_marker'), ('revision', 'draft-2')]:
            with self.subTest(key=key):
                bad = copy.deepcopy(self.record)
                bad['character'][key] = value
                self.path.write_bytes(canonical(bad))
                with self.assertRaisesRegex(ArtError, 'caller expectation'):
                    self.check()

    def test_reference_and_output_tampering_and_missing_files(self):
        for name in ('reference.svg', 'design.svg'):
            with self.subTest(name=name):
                path = self.path.parent / name
                original = path.read_bytes()
                path.write_bytes(original + b'changed')
                with self.assertRaisesRegex(ArtError, 'SHA-256 mismatch'):
                    self.check()
                path.unlink()
                with self.assertRaisesRegex(ArtError, 'missing file'):
                    self.check()
                path.write_bytes(original)

    def test_independent_record_pin_catches_rehashed_substitution(self):
        pin = digest(self.path)
        self.assertTrue(self.check(expected_record_sha256=pin)['record_matches_independent_expectation'])
        output = self.path.parent / self.record['output']['path']
        output.write_text('different bytes, updated self-declaration')
        self.record['output']['sha256'] = digest(output)
        self.write()
        self.assertTrue(self.check()['local_file_hashes_match'])
        with self.assertRaisesRegex(ArtError, 'independent expectation'):
            self.check(expected_record_sha256=pin)

    def test_pin_binds_reference_roles_sources_and_output_mapping(self):
        pin = digest(self.path)
        variants = []
        changed = copy.deepcopy(self.record)
        changed['references'][0]['role'] = 'style'
        variants.append(changed)
        changed = copy.deepcopy(self.record)
        changed['references'][0].update(self.record['output'])
        changed['output'] = {key: self.record['references'][0][key] for key in ('path', 'sha256')}
        variants.append(changed)
        for record in variants:
            self.path.write_bytes(canonical(record))
            self.check()  # Internally consistent declarations alone cannot establish intended roles.
            with self.assertRaisesRegex(ArtError, 'independent expectation'):
                self.check(expected_record_sha256=pin)

    def test_bad_hashes_and_structure_fail_closed(self):
        cases = [([], None), (['schema_version'], True), (['schema_version'], 2),
                 (['kind'], 'runtime'), (['character'], []), (['character', 'revision'], 1),
                 (['stage'], []), (['references'], {}), (['references'], [None]),
                 (['references', 0, 'role'], '../body'), (['references', 0, 'sha256'], 'wrong'),
                 (['output', 'sha256'], 'A' * 64), (['output'], []),
                 (['producer'], {}), (['producer', 'model'], {'id': 'generic'}),
                 (['producer', 'work'], None), (['capture'], {}), (['capture'], {'camera': 1}),
                 (['limitations'], []), (['limitations'], 'unknown'),
                 (['review', 'status'], 'approved'), (['review', 'reviewer'], 'invented'),
                 (['review', 'basis_sha256'], '0' * 64)]
        for path, value in cases:
            bad = copy.deepcopy(self.record)
            if not path:
                bad = value
            else:
                current = bad
                for key in path[:-1]:
                    current = current[key]
                current[path[-1]] = value
            with self.subTest(path=path), self.assertRaises(ArtError):
                validate_record(bad)
        for key in ('character', 'producer', 'output', 'review'):
            bad = copy.deepcopy(self.record)
            bad[key]['unexpected'] = True
            with self.subTest(key=key), self.assertRaises(ArtError):
                validate_record(bad)
        with self.assertRaisesRegex(ArtError, 'SHA-256'):
            self.check(expected_record_sha256='invalid')

    def test_bad_json_duplicate_keys_and_missing_record(self):
        for raw in ('{', '{"kind":1,"kind":2}', '[]', 'null'):
            self.path.write_text(raw)
            with self.subTest(raw=raw), self.assertRaises(ArtError):
                self.check()
        self.path.write_bytes(b'\xff')
        with self.assertRaises(ArtError):
            self.check()
        self.path.unlink()
        with self.assertRaises(OSError):
            self.check()

    def test_unsafe_paths_for_both_inputs_and_output(self):
        for field in ('reference', 'output'):
            for path in ('../reference.svg', '/tmp/out.svg', 'a//b.svg', './reference.svg',
                         'a\\b.svg', 'C:out.svg', 'a/../reference.svg', '.', ''):
                bad = copy.deepcopy(self.record)
                item = bad['references'][0] if field == 'reference' else bad['output']
                item['path'] = path
                self.path.write_bytes(canonical(bad))
                with self.subTest(field=field, path=path), self.assertRaises(ArtError):
                    self.check()

    def test_symlink_escape_and_directory_are_rejected(self):
        outside = self.root / 'outside.svg'
        outside.write_bytes((self.path.parent / 'design.svg').read_bytes())
        (self.path.parent / 'link.svg').symlink_to(outside)
        for name in ('link.svg', 'nested'):
            (self.path.parent / 'nested').mkdir(exist_ok=True)
            self.record['output']['path'] = name
            self.write()
            with self.subTest(name=name), self.assertRaisesRegex(ArtError, 'missing file or escaped directory'):
                self.check()

    def test_duplicate_references_and_output_alias_fail(self):
        original = copy.deepcopy(self.record)
        self.record['references'].append(copy.deepcopy(self.record['references'][0]))
        self.write()
        with self.assertRaisesRegex(ArtError, 'duplicate'):
            self.check()
        self.record = original
        self.record['output'] = {key: self.record['references'][0][key] for key in ('path', 'sha256')}
        self.write()
        with self.assertRaisesRegex(ArtError, 'duplicate'):
            self.check()

    def test_existing_human_review_is_bound_but_never_minted(self):
        for status in ('accepted', 'rejected'):
            self.record['review'] = {'status': status, 'reviewer': 'Synthetic reviewer assertion',
                                     'notes': 'Only tests record binding; not a real approval.',
                                     'basis_sha256': review_basis(self.record)}
            self.write()
            report = self.check()
            self.assertEqual(report['declared_human_review_status'], status)
            self.assertEqual(report['art_approval'], 'not_determined_by_tool')
        for field in ('character', 'stage', 'references', 'producer', 'output', 'limitations'):
            bad = copy.deepcopy(self.record)
            if field == 'character': bad[field]['revision'] = 'draft-2'
            elif field == 'stage': bad[field] = 'pose_study'
            elif field == 'references': bad[field][0]['role'] = 'pose'
            elif field == 'producer': bad[field]['version'] = 'fixture-2'
            elif field == 'output': bad[field]['sha256'] = '0' * 64
            else: bad[field].append('Additional known limitation.')
            with self.subTest(field=field), self.assertRaisesRegex(ArtError, 'stale basis'):
                validate_record(bad)

    def test_provider_substitution_and_optional_capture_are_declarations(self):
        self.record['producer'] = {'name': 'alternative_renderer', 'version': '2',
                                  'model': {'id': 'synthetic_model', 'revision': 'r1'},
                                  'work': {'id': 'synthetic_work', 'revision': 'r3'}}
        self.record['capture'] = {'camera': 'orthographic front; synthetic', 'pose': 'neutral marker'}
        self.record['stage'] = 'pose_study'
        self.write()
        self.assertEqual(self.check()['semantic_correctness'], 'not_verified')

    def test_direct_concept_needs_no_reference_or_pixel_constraints(self):
        self.record['stage'] = 'concept'
        self.record['references'] = []
        self.write()
        self.check()  # SVG with soft opacity and arbitrary canvas; no PNG/palette/frame parser.

    def test_relocated_standalone_cli_and_failure_exit(self):
        portable = self.root / 'portable'
        module = portable / 'tools/art'
        module.mkdir(parents=True)
        for name in ('__init__.py', 'manifest.py', 'design.py'):
            shutil.copy2(ROOT / 'tools/art' / name, module / name)
        shutil.copytree(self.path.parent, portable / 'fixture')
        argv = [sys.executable, '-m', 'tools.art.design', 'fixture/record.json',
                '--character-id', 'sample_marker', '--revision', 'draft-1']
        success = subprocess.run(argv, cwd=portable, capture_output=True, text=True)
        self.assertEqual(success.returncode, 0, success.stderr)
        failure = subprocess.run(argv[:-1] + ['wrong'], cwd=portable, capture_output=True, text=True)
        self.assertEqual(failure.returncode, 1)
        self.assertIn('caller expectation', failure.stderr)
        self.assertNotIn('Traceback', failure.stderr)


if __name__ == '__main__':
    unittest.main()
