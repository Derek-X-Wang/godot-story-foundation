"""Synthetic record tests, not art approval or genuine gameplay evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'tools/production/production.py'
spec = importlib.util.spec_from_file_location('production', SOURCE)
production = importlib.util.module_from_spec(spec)
spec.loader.exec_module(production)


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name) / 'workspace'
        production.start(self.workspace)
        self.authoring = self.workspace / 'authoring'
        self.record = self.authoring / 'production.json'
        self.data = json.loads((ROOT / 'tools/production/examples/perspective-scene.json').read_text())
        for ref in self.data['references'].values():
            ref['status'] = 'accepted'
        self.data['assets'][0]['status'] = 'accepted'
        (self.workspace / 'game/scene.txt').write_text('SYNTHETIC candidate; not a running game')

    def save(self):
        self.record.write_bytes(production.canonical(self.data))

    def seal(self, gate):
        r = self.data['reviews'][gate]
        r.update(candidate_sha256=production.candidate_digest(self.data, self.authoring), candidate_revision=self.data['revision'])
        r['basis_sha256'] = production.identity(self.data, gate)

    def accept(self, gate):
        sha = production.candidate_digest(self.data, self.authoring)
        r = self.data['reviews'][gate]
        r.update(decision='accepted', reviewer='Synthetic fixture', reviewer_kind='synthetic', reviewed_at='2026-10-20T00:00:00Z', scope='Synthetic test only', evidence=[], checks=[])
        for view in self.data['presentation']['viewports']:
            for state in self.data['presentation']['states']:
                name = f'{gate}-{view}-{state}.txt'
                raw = b'SYNTHETIC declared playback: not rendered gameplay'
                (self.authoring / name).write_bytes(raw)
                r['evidence'].append(dict(path=name, sha256=hashlib.sha256(raw).hexdigest(), kind='playback', scope='Synthetic', platform='synthetic', viewport=view, route_state=state, candidate_sha256=sha))
        if gate != 'composition':
            name = f'{gate}-check.txt'
            raw = b'SYNTHETIC check report'
            (self.authoring / name).write_bytes(raw)
            r['evidence'].append(dict(path=name, sha256=hashlib.sha256(raw).hexdigest(), kind='check_report', scope='Synthetic', platform='synthetic', viewport='not applicable', route_state='not applicable', candidate_sha256=sha))
            r['checks'].append(dict(name='synthetic check', result='passed', evidence_path=name))
        self.seal(gate)

    def ready(self):
        for gate in production.REVIEW_GATES:
            self.accept(gate)

    def check(self, gate='release'):
        production.check(self.data, self.authoring, gate, allow_test_fixture=True)

    def test_new_project_default_surfaces_requirements_and_has_no_approval(self):
        data = production.load(self.record)
        guide = (self.workspace / 'AGENTS.md').read_text()
        for required in ('--gate flow', '--gate brief', '--gate composition', '--gate integration', '--gate release', 'actual composition', 'pose cut'):
            self.assertIn(required, guide)
        self.assertTrue(all(r['decision'] == 'pending' for r in data['reviews'].values()))
        result = subprocess.run([sys.executable, self.workspace / 'tools/production.py', 'check', self.record, '--gate', 'flow'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('project: fill', result.stderr)
        self.assertFalse((self.workspace / 'game/project.godot').exists())

    def test_flow_only_does_not_require_art_or_visual_acceptance(self):
        self.data['presentation'] = {}
        del self.data['references']['art']
        del self.data['references']['composition']
        self.check('flow')
        with self.assertRaises(production.Invalid):
            self.check('brief')

    def test_both_public_briefs_and_custom_static_are_supported(self):
        for name in ('symbolic-rpg', 'perspective-scene'):
            data = json.loads((ROOT / f'tools/production/examples/{name}.json').read_text())
            production.check(data, self.authoring, 'brief', True)
            with self.assertRaisesRegex(production.Invalid, 'synthetic fixture'):
                production.check(data, self.authoring, 'brief')
        self.data['presentation']['convention'] = 'custom'
        self.data['presentation']['movement']['mode'] = 'none'
        self.accept('composition')
        self.data['reviews']['composition']['evidence'][0]['kind'] = 'rendered_still'
        self.seal('composition')
        self.check('composition')

    def test_missing_decisions_fail_actionably(self):
        for path in [('presentation', 'convention'), ('presentation', 'world_scale'), ('presentation', 'viewports'), ('presentation', 'states'), ('presentation', 'ui', 'essential_visibility'), ('presentation', 'ui', 'portraits'), ('references', 'art', 'identity')]:
            with self.subTest(path=path):
                data = copy.deepcopy(self.data)
                target = data
                for key in path[:-1]: target = target[key]
                del target[path[-1]]
                with self.assertRaises(production.Invalid): production.check(data, self.authoring, 'brief', True)

    def test_release_record_and_read_only_cli(self):
        self.ready(); self.check(); self.save()
        before = self.record.read_bytes()
        result = subprocess.run([sys.executable, SOURCE, 'check', self.record, '--gate', 'release', '--allow-test-fixture'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('not automatic visual approval', result.stdout)
        self.assertEqual(before, self.record.read_bytes())

    def test_relocated_starter_runs_without_foundation_checkout(self):
        self.ready(); self.save()
        relocated = self.workspace.parent / 'relocated'
        self.workspace.rename(relocated)
        result = subprocess.run([sys.executable, relocated / 'tools/production.py', 'check', relocated / 'authoring/production.json', '--gate', 'release', '--allow-test-fixture'], cwd=relocated, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Permission is hereby granted', (relocated / 'tools/production.py').read_text())

    def test_stale_candidate_including_untracked_and_deleted_file_fails(self):
        for change in ('changed', 'added', 'deleted'):
            with self.subTest(change=change):
                self.ready()
                target = self.workspace / 'game/scene.txt'
                if change == 'changed': target.write_text('changed')
                if change == 'added': (self.workspace / 'game/new.txt').write_text('untracked')
                if change == 'deleted': target.unlink()
                with self.assertRaisesRegex(production.Invalid, 'candidate source/build changed'): self.check()
                target.write_text('restored')
                (self.workspace / 'game/new.txt').unlink(missing_ok=True)

    def test_rebinding_review_alone_cannot_reuse_old_capture(self):
        self.ready()
        (self.workspace / 'game/scene.txt').write_text('new candidate')
        self.seal('release')
        with self.assertRaisesRegex(production.Invalid, 'different candidate'): self.check()

    def test_earlier_direction_can_remain_historical(self):
        self.accept('composition')
        old = self.data['reviews']['composition']['candidate_sha256']
        self.data['revision'] = 'next-build'
        (self.workspace / 'game/scene.txt').write_text('new integrated source')
        self.accept('integration'); self.accept('release'); self.check()
        self.assertNotEqual(old, self.data['reviews']['release']['candidate_sha256'])

    def test_changed_capture_and_binding_fields_fail(self):
        self.ready()
        evidence = self.data['reviews']['release']['evidence'][0]
        (self.authoring / evidence['path']).write_text('replacement')
        with self.assertRaisesRegex(production.Invalid, 'evidence bytes changed'): self.check()
        for change in ('reviewer', 'scope', 'reviewed_at'):
            self.ready()
            self.data['reviews']['release'][change] = 'changed'
            with self.assertRaisesRegex(production.Invalid, 'stale/missing review binding'): self.check()
        self.ready(); self.data['presentation']['world_scale'] = 'changed'
        with self.assertRaisesRegex(production.Invalid, 'stale/missing review binding'): self.check()

    def test_changed_local_reference_fails_even_same_source_path(self):
        target = self.authoring / 'reference.txt'; target.write_bytes(b'accepted reference')
        self.data['references']['art'].update(kind='local', source='reference.txt', identity=hashlib.sha256(target.read_bytes()).hexdigest())
        self.ready(); self.check()
        target.write_text('replacement reference')
        with self.assertRaisesRegex(production.Invalid, 'evidence bytes changed'): self.check()

    def test_provisional_reference_and_placeholder_cannot_close_integration(self):
        self.ready()
        self.data['references']['art']['status'] = 'provisional'
        with self.assertRaisesRegex(production.Invalid, 'resolve provisional'): self.check()
        self.data['references']['art']['status'] = 'accepted'
        self.data['assets'][0]['status'] = 'placeholder'
        with self.assertRaisesRegex(production.Invalid, 'placeholder/candidate'): self.check()
        self.accept('composition'); self.check('composition')

    def test_pending_review_not_accepted_by_identity(self):
        self.ready(); self.data['reviews']['release']['decision'] = 'pending'; self.save()
        result = subprocess.run([sys.executable, SOURCE, 'identity', self.record, '--gate', 'release'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(production.load(self.record)['reviews']['release']['decision'], 'pending')
        with self.assertRaisesRegex(production.Invalid, 'explicit acceptance'): self.check()

    def test_ineligible_visual_evidence_and_motion_stills_fail(self):
        for kind in ('headless', 'mockup', 'offscreen_sampler', 'check_report', 'rendered_still'):
            with self.subTest(kind=kind):
                self.accept('composition')
                self.data['reviews']['composition']['evidence'][0]['kind'] = kind
                self.seal('composition')
                with self.assertRaises(production.Invalid): self.check('composition')

    def test_cartesian_viewport_state_coverage(self):
        self.data['presentation'].update(viewports=['wide','narrow'], states=['entry','dialogue'])
        self.ready(); self.check()
        r = self.data['reviews']['release']
        r['evidence'] = [e for e in r['evidence'] if e['kind'] == 'check_report' or (e['viewport'], e['route_state']) in {('wide','entry'),('narrow','dialogue')}]
        self.seal('release')
        with self.assertRaisesRegex(production.Invalid, 'every declared viewport/state pair'): self.check()

    def test_wrong_target_or_duplicate_evidence_fails(self):
        self.ready(); r = self.data['reviews']['release']
        r['evidence'][0]['viewport'] = 'other'
        self.seal('release')
        with self.assertRaisesRegex(production.Invalid, 'outside declared targets'): self.check()
        self.ready(); r = self.data['reviews']['release']; r['evidence'].append(copy.deepcopy(r['evidence'][0]))
        self.seal('release')
        with self.assertRaisesRegex(production.Invalid, 'duplicate artifact/target'): self.check()

    def test_missing_failed_blocked_unrun_checks_fail(self):
        for result in ('failed', 'blocked', 'unrun'):
            self.ready(); self.data['reviews']['release']['checks'][0]['result'] = result; self.seal('release')
            with self.assertRaisesRegex(production.Invalid, 'cannot close this gate'): self.check()
        self.ready(); self.data['reviews']['release']['checks'] = []; self.seal('release')
        with self.assertRaisesRegex(production.Invalid, 'applicable focused/final'): self.check()

    def test_path_escape_and_symlink_inputs_rejected(self):
        self.ready()
        evidence = self.data['reviews']['release']['evidence'][0]
        for path in ('../escape.txt', str(self.authoring / evidence['path'])):
            bad = dict(evidence, path=path)
            with self.assertRaises(production.Invalid): production.artifact(self.authoring, bad, 'evidence')
        outside = self.workspace / 'outside.txt'; outside.write_text('outside')
        (self.authoring / 'alias.txt').symlink_to(outside)
        with self.assertRaises(production.Invalid): production.artifact(self.authoring, dict(evidence,path='alias.txt'), 'evidence')
        (self.workspace / 'game/alias').symlink_to(outside)
        with self.assertRaisesRegex(production.Invalid, 'symlink'): production.candidate_digest(self.data, self.authoring)

    def test_candidate_ancestor_symlink_and_authoring_inclusion_rejected(self):
        (self.workspace / 'alias').symlink_to(self.workspace / 'game', target_is_directory=True)
        self.data['candidate_path'] = 'alias'
        with self.assertRaisesRegex(production.Invalid, 'symlink'): production.candidate_digest(self.data, self.authoring)
        self.data['candidate_path'] = '.'
        with self.assertRaisesRegex(production.Invalid, 'exclude the authoring'): production.candidate_digest(self.data, self.authoring)

    def test_init_rejects_overwrite_and_export_root_even_via_symlink(self):
        with self.assertRaisesRegex(production.Invalid, 'already exists'): production.start(self.workspace)
        game = self.workspace / 'game'; (game / 'project.godot').write_text('; synthetic')
        (game / 'sub').mkdir(); (self.workspace / 'alias').symlink_to(game / 'sub', target_is_directory=True)
        for parent in (game, self.workspace / 'alias'):
            with self.assertRaisesRegex(production.Invalid, 'outside a Godot'): production.start(parent / 'new')
        self.assertFalse((game / 'sub/new').exists())

    def test_malformed_json_schema_and_synthetic_reviewer_fail(self):
        for raw in ('{"a":1,"a":2}', '{"a":NaN}', '[]', '{'):
            self.record.write_text(raw)
            self.assertEqual(production.main(['check',str(self.record),'--gate','flow']), 1)
        for version in (2, True, '1'):
            self.data['schema_version'] = version
            with self.assertRaisesRegex(production.Invalid, 'schema_version'): self.check('flow')
        self.data['schema_version'] = 1; self.ready(); self.data['test_fixture'] = False
        with self.assertRaisesRegex(production.Invalid, 'synthetic reviewer'): self.check()


if __name__ == '__main__':
    unittest.main()
