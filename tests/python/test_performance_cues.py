"""Neutral data-contract tests; not rendered or emotional acceptance."""
import copy
import json
import subprocess
import sys
import unittest
import test_production_workflow as workflow
production = workflow.production


class CueTests(unittest.TestCase):
    setUp = workflow.ProductionTests.setUp
    save = workflow.ProductionTests.save
    seal = workflow.ProductionTests.seal
    accept = workflow.ProductionTests.accept
    ready = workflow.ProductionTests.ready
    check = workflow.ProductionTests.check

    def manifest(self):
        return {
            'capabilities': {'pose': ['rest', 'alert'], 'frame': ['wide', 'detail']},
            'cues': {'arrival.notice': {'pose': 'alert'}, 'departure.look': {'frame': 'wide'}},
            'beats': [
                {'id': 'arrival.notice', 'performance': {'pose': 'alert'}},
                {'id': 'arrival.pause', 'performance': {}},
                {'id': 'departure.look', 'performance': {'frame': 'wide'}},
            ],
        }

    def test_two_sequences_reorder_insert_and_custom_capabilities(self):
        data = self.manifest()
        production.check_cues(data)
        data['beats'].reverse()
        data['beats'].insert(1, {'id': 'departure.pause', 'performance': {}})
        production.check_cues(data)
        production.check_cues({'capabilities': {}, 'cues': {}, 'beats': []})
        data = {'capabilities': {'lamp': ['on']}, 'cues': {'room.light': {'lamp': 'on'}},
                'beats': [{'id': 'room.light', 'performance': {'lamp': 'on'}}]}
        production.check_cues(data)

    def test_reject_invalid_bindings_and_shapes(self):
        mutations = [
            lambda d: d['beats'].append(copy.deepcopy(d['beats'][0])),
            lambda d: d['beats'].pop(0),
            lambda d: d['beats'][0].update(id='unknown'),
            lambda d: d['beats'][0].update(performance={}),
            lambda d: d['beats'][0].update(performance={'pose': 'rest'}),
            lambda d: d['beats'][1].update(performance={'pose': 'alert'}),
            lambda d: d['cues']['arrival.notice'].update(timer='1'),
            lambda d: d['cues']['arrival.notice'].update(pose='unknown'),
            lambda d: d['cues'].update({'empty': {}}),
            lambda d: d['capabilities'].update(pose=['rest', 'rest']),
            lambda d: d['capabilities'].update(pose=[True]),
            lambda d: d['capabilities'].update(pose=[]),
            lambda d: d['beats'][0].update(id=[]),
            lambda d: d['beats'][0].update(id=' '),
            lambda d: d['beats'][0].update(performance=[]),
            lambda d: d['beats'][0].update(extra='typo'),
            lambda d: d.update(beats={}),
            lambda d: d.update(cues=[]),
            lambda d: d.update(capabilities=[]),
            lambda d: d.update(extra='typo'),
        ]
        for change in mutations:
            data = self.manifest()
            change(data)
            with self.subTest(data=data), self.assertRaises(production.Invalid):
                production.check_cues(data)

    def test_optional_inline_gate_and_review_binding(self):
        self.ready()
        self.check()
        old = production.identity(self.data, 'release')
        self.data['performance_cues'] = self.manifest()
        self.assertNotEqual(old, production.identity(self.data, 'release'))
        with self.assertRaisesRegex(production.Invalid, 'stale/missing review binding'):
            self.check()
        self.ready()
        self.check()
        self.data['performance_cues']['beats'][0]['performance'] = {}
        for gate in production.GATES:
            with self.subTest(gate=gate), self.assertRaisesRegex(production.Invalid, 'binding drift'):
                self.check(gate)
        del self.data['performance_cues']
        self.assertEqual(old, production.identity(self.data, 'release'))

    def test_portable_cli_and_generated_recipe(self):
        path = self.authoring / 'cues.json'
        path.write_text(json.dumps(self.manifest()))
        script = self.workspace / 'tools/production.py'
        result = subprocess.run([sys.executable, script, 'check-cues', path], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('not proof of rendering', result.stdout)
        path.write_text('{"cues": {}, "cues": {}}')
        self.assertEqual(production.main(['check-cues', str(path)]), 1)
        guide = (self.authoring / 'release-smoke.md').read_text()
        for phrase in ('check-cues', 'actual consumer resolver', 'texture/atlas region',
                       'history/modal', 'rendered_sequence/playback', 'state purity'):
            self.assertIn(phrase, guide)
        self.assertIn('check-cues', (self.workspace / 'AGENTS.md').read_text())
