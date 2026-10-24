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
        (self.workspace / 'game/build').mkdir()
        (self.workspace / 'game/build/game.pck').write_text('SYNTHETIC export; not executable')
        self.data['verification']['export_path'] = 'build/game.pck'

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
                r['evidence'].append(dict(path=name, sha256=hashlib.sha256(raw).hexdigest(), kind='playback', scope='Synthetic', platform=self.data['verification']['primary_target'], viewport=view, route_state=state, candidate_sha256=sha))
        if gate != 'composition':
            name = f'{gate}-check.txt'
            raw = b'SYNTHETIC check report'
            (self.authoring / name).write_bytes(raw)
            r['evidence'].append(dict(path=name, sha256=hashlib.sha256(raw).hexdigest(), kind='check_report', scope='Synthetic', platform=self.data['verification']['primary_target'], viewport='not applicable', route_state='not applicable', candidate_sha256=sha))
            lanes = {'synthetic check'}
            if gate == 'release':
                lanes = production.RELEASE_LANES | ({'javascript_bridge'} if self.data['verification']['javascript_bridge'] == 'present' else set())
            r['checks'].extend(dict(name=lane, result='passed', evidence_path=name) for lane in sorted(lanes))
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

    def test_generated_release_guide_is_portable_and_pending(self):
        guide = (self.authoring / 'release-smoke.md').read_text()
        for phrase in ('normal_export_entry', 'settled_ui_geometry', 'javascript_bridge',
                       'outside assert expressions', 'Node/JS mocks alone', 'integer 1/0',
                       'versioned JSON', 'phantom rectangles', 'global-frontmost',
                       'human attention', 'Safari', 'not implicit release gates'):
            self.assertIn(phrase, guide)
        data = production.load(self.record)
        self.assertEqual(data['schema_version'], 2)
        self.assertEqual(data['verification']['primary_target'], 'Chrome (cloud)')
        self.assertEqual({c['name'] for c in data['reviews']['release']['checks']}, production.RELEASE_LANES)
        self.assertTrue(all(c['result'] == 'unrun' for c in data['reviews']['release']['checks']))
        relocated = self.workspace.parent / 'moved'
        self.workspace.rename(relocated)
        self.assertEqual((relocated / 'authoring/release-smoke.md').read_text(), guide)
        subprocess.run([sys.executable, relocated / 'tools/production.py', 'init',
                        '--output', relocated.parent / 'another'], check=True, capture_output=True)
        self.assertEqual((relocated.parent / 'another/authoring/release-smoke.md').read_text(), guide)

    def test_generated_timed_recipe_preserves_scope_and_evidence_boundaries(self):
        guide = (self.authoring / 'release-smoke.md').read_text()
        section = guide.split('## Timed presentation: input intent and recoverable facts\n', 1)[1].split('## Visibility and interruption', 1)[0]
        normalized = ' '.join(section.split())
        for boundary in ('not a universal permanent transcript requirement',
                         'finite measurement window', 'fresh press/release',
                         'separately from held/repeated input and stale callbacks',
                         'first manual result', 'independently earned fact',
                         'Missing earned content and revealing unearned content must fail',
                         'must not grant knowledge or duplicate effects',
                         'normal-entry rendered transition evidence',
                         'adds no schema, runtime or mandatory release lane'):
            self.assertIn(boundary, normalized)
        self.assertIn('input epochs alone are not proof',
                      (self.workspace / 'AGENTS.md').read_text())
        # Template persistence only: not execution of consumer input/receipt tests.
        self.assertEqual({c['name'] for c in production.load(self.record)['reviews']['release']['checks']},
                         production.RELEASE_LANES)

    def test_generated_coverage_recipe_neutral_counterexamples(self):
        guide = (self.authoring / 'release-smoke.md').read_text()
        section = guide.split('## Optional scoped presentation coverage\n', 1)[1].split('## Optional performance cue bindings', 1)[0]
        self.assertIn('presentation_coverage', (self.workspace / 'AGENTS.md').read_text())
        for boundary in ('independent expectation', 'consumer owns both traversal',
                         'not "all histories"', 'adds no schema field or mandatory lane',
                         'does not prove', 'natural-player discovery'):
            self.assertIn(boundary, ' '.join(section.split()))
        # Execute only the shipped synthetic illustration, not an engine or
        # an invented proof that a consumer's reachable inventory is complete.
        namespace = {}
        exec(section.split('```python\n', 1)[1].split('```', 1)[0], namespace)
        expected = namespace['expected']
        validate = namespace['check_presentation']
        validate(expected, copy.deepcopy(expected))  # Includes explicit text mode.
        mutations = [
            ('terminal', ('visual', [])),
            ('restored', ('text', ['text'])),
            ('restored', ('visual', ['scene', 'text'])),
        ]
        for state, actual in mutations:
            with self.subTest(state=state, actual=actual):
                observed = copy.deepcopy(expected)
                observed[state] = actual
                with self.assertRaisesRegex(ValueError, 'presentation mismatch'):
                    validate(expected, observed)
        observed = copy.deepcopy(expected)
        del observed['terminal']
        with self.assertRaisesRegex(ValueError, 'inventory mismatch'):
            validate(expected, observed)
        observed = copy.deepcopy(expected)
        observed['undeclared_terminal'] = ('text', ['text'])
        with self.assertRaisesRegex(ValueError, 'inventory mismatch'):
            validate(expected, observed)

    def test_optional_coverage_uses_existing_check_report_and_identity(self):
        self.ready()
        review = self.data['reviews']['integration']
        report_path = next(e['path'] for e in review['evidence'] if e['kind'] == 'check_report')
        lane = dict(name='presentation_coverage', result='passed', evidence_path=report_path)
        review['checks'].append(lane)
        self.seal('integration')
        self.check('integration')
        for status in ('failed', 'blocked', 'unrun'):
            lane['result'] = status
            self.seal('integration')
            with self.assertRaisesRegex(production.Invalid, 'failed, blocked or unrun'):
                self.check('integration')
        lane['result'] = 'passed'
        self.seal('integration')
        (self.authoring / report_path).write_text('Changed SYNTHETIC coverage report')
        with self.assertRaisesRegex(production.Invalid, 'evidence bytes changed'):
            self.check('integration')

    def test_v1_history_still_checks_until_release_with_actionable_migration(self):
        self.ready()
        self.data['schema_version'] = 1
        del self.data['verification']
        for gate in production.REVIEW_GATES:
            self.seal(gate)
        for gate in ('flow', 'brief', 'composition', 'integration'):
            self.check(gate)
        with self.assertRaisesRegex(production.Invalid, 'version 2 verification'):
            self.check()

    def test_primary_target_and_bridge_are_brief_decisions_not_flow_blockers(self):
        for field, value in [('primary_target', ''), ('javascript_bridge', ''),
                             ('optional_targets', ['Safari', 'Safari']),
                             ('optional_targets', [self.data['verification']['primary_target']])]:
            with self.subTest(field=field, value=value):
                data = copy.deepcopy(self.data)
                data['verification'][field] = value
                production.check(data, self.authoring, 'flow', True)
                with self.assertRaises(production.Invalid):
                    production.check(data, self.authoring, 'brief', True)
        self.data['verification']['export_path'] = ''
        self.check('brief')
        self.accept('composition'); self.check('composition')

    def test_native_and_web_primary_targets_do_not_require_safari(self):
        for target, bridge in [('Godot native (Linux)', 'none'), ('Chrome (cloud)', 'present'), ('Firefox (Linux)', 'present')]:
            with self.subTest(target=target):
                self.data['verification'].update(primary_target=target, javascript_bridge=bridge,
                                                 optional_targets=['Safari (not planned)'])
                self.ready(); self.check()

    def test_release_requires_export_and_settled_ui_lanes_on_primary(self):
        for lane in production.RELEASE_LANES:
            self.ready()
            r = self.data['reviews']['release']
            r['checks'] = [c for c in r['checks'] if c['name'] != lane]
            self.seal('release')
            with self.assertRaisesRegex(production.Invalid, lane): self.check()
        self.ready()
        self.data['reviews']['release']['checks'].append(copy.deepcopy(self.data['reviews']['release']['checks'][0]))
        self.seal('release')
        with self.assertRaisesRegex(production.Invalid, 'exactly one'): self.check()
        for platform in ('Node mock', 'Safari', 'source debug'):
            self.ready()
            report = next(e for e in self.data['reviews']['release']['evidence'] if e['kind'] == 'check_report')
            report['platform'] = platform
            self.seal('release')
            with self.assertRaisesRegex(production.Invalid, 'declared primary target'): self.check()

    def test_actual_bridge_lane_required_only_when_declared_present(self):
        self.ready(); self.check()  # Native/no bridge needs no invented bridge check.
        self.data['verification'].update(primary_target='Chrome (cloud)', javascript_bridge='present')
        self.ready(); self.check()
        r = self.data['reviews']['release']
        r['checks'] = [c for c in r['checks'] if c['name'] != 'javascript_bridge']
        self.seal('release')
        with self.assertRaisesRegex(production.Invalid, 'javascript_bridge'): self.check()

    def test_release_export_path_is_required_inside_fingerprinted_candidate(self):
        for path in ('', '.', '../other.pck', '/tmp/game.pck', 'missing.pck', '.godot/game.pck', '.git/objects'):
            with self.subTest(path=path):
                self.ready()
                self.data['verification']['export_path'] = path
                self.seal('release')
                with self.assertRaisesRegex(production.Invalid, 'verification.export_path'): self.check()
        self.data['verification']['export_path'] = 'build'  # Multi-file Web export directory.
        self.ready(); self.check()
        (self.workspace / 'game/build/game.pck').write_text('changed export')
        with self.assertRaisesRegex(production.Invalid, 'candidate source/build changed'): self.check()

    def test_export_directory_cannot_contain_only_excluded_cache_bytes(self):
        cache = self.workspace / 'game/cache-only/.godot'
        cache.mkdir(parents=True)
        (cache / 'not-a-release.pck').write_text('not fingerprinted')
        self.data['verification']['export_path'] = 'cache-only'
        self.ready()
        with self.assertRaisesRegex(production.Invalid, 'verification.export_path'): self.check()

    def test_target_policy_change_invalidates_review_binding(self):
        self.ready()
        self.data['verification']['optional_targets'] = ['Safari (optional)']
        with self.assertRaisesRegex(production.Invalid, 'stale/missing review binding'): self.check()

    def test_release_rendered_evidence_cannot_substitute_optional_target(self):
        self.ready()
        self.data['reviews']['release']['evidence'][0]['platform'] = 'Safari'
        self.seal('release')
        with self.assertRaisesRegex(production.Invalid, 'rendered evidence must use the primary target'): self.check()

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
        for version in (3, True, '1'):
            self.data['schema_version'] = version
            with self.assertRaisesRegex(production.Invalid, 'schema_version'): self.check('flow')
        self.data['schema_version'] = 2; self.ready(); self.data['test_fixture'] = False
        with self.assertRaisesRegex(production.Invalid, 'synthetic reviewer'): self.check()


if __name__ == '__main__':
    unittest.main()

