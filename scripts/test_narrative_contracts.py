#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
"""Run neutral bounded-contract examples through the existing regression runner.

Godot 4.6.3 and Python 3.11+ only. Separate helper-only and real-kernel projects;
no Dialogue Manager, art, autoload or game assets. Mutation results must contain
the expected semantic violation, not merely a parser error or failed process.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.regression.runner import run_manifest

FILES = {
    'narrative_contract.gd': 'addons/story_foundation/testing/narrative_contract.gd',
    'narrative_contract.gd.uid': 'addons/story_foundation/testing/narrative_contract.gd.uid',
    'replay_record.gd': 'addons/story_foundation/testing/replay_record.gd',
    'replay_record.gd.uid': 'addons/story_foundation/testing/replay_record.gd.uid',
    'neutral_adapter.gd': 'examples/narrative_contracts/neutral_adapter.gd',
    'run.gd': 'examples/narrative_contracts/run.gd',
    'test_narrative_contract.gd': 'tests/regression/test_narrative_contract.gd',
}


def check(godot: str = 'godot', output: Path = ROOT / '.build/narrative-contracts') -> None:
    executable = shutil.which(godot)
    if executable is None:
        raise SystemExit(f'Godot not found: {godot}; use --godot PATH')
    with tempfile.TemporaryDirectory(prefix='foundation-narrative-contract-') as temporary:
        base = Path(temporary)
        env_args = []
        for name in ('XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
            directory = base / name.lower()
            directory.mkdir()
            env_args.append(f'{name}={directory}')
        project = base / 'isolated'
        project.mkdir()
        (project / 'project.godot').write_text('config_version=5\n[application]\n'
            'config/name="Neutral narrative contracts"\n[rendering]\n'
            'renderer/rendering_method="gl_compatibility"\n')
        for target, source in FILES.items():
            shutil.copyfile(ROOT / source, project / target)
        assert {p.name for p in project.iterdir()} == set(FILES) | {'project.godot'}

        def run(where: Path, name: str, *, units=False, kernel=False, mutation='') -> dict:
            command = ['env', *env_args, executable, '--headless', '--path', str(where),
                       '--script', 'res://test_narrative_contract.gd' if units else 'res://run.gd']
            arguments = (['--kernel'] if kernel else []) + (['--mutation', mutation] if mutation else [])
            if arguments:
                command += ['--', *arguments]
            suite = {'id': 'narrative_units' if units else 'narrative_example', 'lane': 'source',
                     'command': command, 'cwd': str(where), 'timeout_seconds': 60,
                     'result_prefix': 'NARRATIVE_RESULT', 'expected_scenario_ids':
                     ['helper_contract' if units else 'kernel_contract' if kernel else 'neutral_contract']}
            report = run_manifest({'schema_version': 1, 'required_lanes': ['source'], 'suites': [suite]},
                                  base_dir=where, output_dir=output / name)
            record = report['suites'][0]
            if not mutation:
                assert report['passed'], record
            else:
                assert not report['passed'] and record['result'] is not None, record
                assert record['returncode'] == 1 and not record['timed_out'] and not record['diagnostics'], record
                assert record['failures'] == ['command exited with status 1',
                    'result reported passed=false', 'result reported nonempty failures'], record
            result = record['result']
            print(f'Narrative {name}: {record["status"]}, {result["checks"]} observations/checks')
            return result

        run(project, 'units', units=True)
        red = run(project, 'red_missing_option', mutation='missing_option')['details']
        assert red['ok'] and 'right_option_required' in {
            item['requirement'] for item in red['shortest_counterexamples']}
        baseline = run(project, 'neutral')['details']
        for mode, requirement in [('missing_option', 'right_option_required'),
                                  ('defer_lock', 'confirmation_remains_available_after_defer')]:
            mutant = run(project, mode, mutation=mode)['details']
            assert mutant['ok'] and mutant['status'] == 'contract_failed'
            assert requirement in {item['requirement'] for item in mutant['shortest_counterexamples']}
        relocated = base / 'relocated'
        shutil.copytree(project, relocated, ignore=shutil.ignore_patterns('.godot'))
        shutil.rmtree(project)
        assert not (relocated / '.godot').exists()
        run(relocated, 'relocated_units', units=True)
        assert run(relocated, 'relocated_neutral')['details'] == baseline

        # Add only the selected kernel's declared source dependency. The generic
        # helper and its first project have already run without any runtime.
        shutil.copyfile(ROOT / 'examples/narrative_contracts/kernel_adapter.gd', relocated / 'kernel_adapter.gd')
        runtime = relocated / 'addons/story_foundation/runtime'
        runtime.mkdir(parents=True)
        for filename in ('rule_kernel.gd', 'actor_record.gd'):
            shutil.copyfile(ROOT / 'addons/story_foundation/runtime' / filename, runtime / filename)
        kernel = run(relocated, 'kernel', kernel=True)['details']
        assert kernel['rejected_kernel_state_unchanged'] and kernel['label_attached_to_tree']
        assert kernel['reverse_order_does_not_satisfy_goal']
        assert len(kernel['shortest_goal_traces']['deferred_then_published_at_cutoff']) == 3
        for mode, requirement in [('stale_projection', 'committed_state_reaches_label'),
                                  ('false_success', 'rejection_must_not_render_success')]:
            mutant = run(relocated, mode, kernel=True, mutation=mode)['details']
            assert mutant['ok'] and mutant['status'] == 'contract_failed'
            assert requirement in {item['requirement'] for item in mutant['shortest_counterexamples']}
            if mode == 'false_success':
                assert mutant['rejected_kernel_state_unchanged'] and mutant['label_attached_to_tree']
                witness = next(item for item in mutant['shortest_counterexamples'] if item['requirement'] == requirement)
                assert witness['trace'] == ['publish']
        assert run(relocated, 'restored_kernel', kernel=True)['details'] == kernel
        # A real source lane pass does not populate browser/native evidence.
        print(f'Narrative bounded BFS: neutral {baseline["states"]} states, kernel {kernel["states"]} states')
    print('Optional narrative contracts passed isolation, fresh relocation, real kernel and four semantic mutation controls')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot', default='godot')
    parser.add_argument('--output', type=Path, default=ROOT / '.build/narrative-contracts')
    args = parser.parse_args()
    check(args.godot, args.output)
