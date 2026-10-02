#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
"""Exercise the optional semantic replay helper in a standalone relocated project.

Only the helper, its unit tests and a neutral synthetic adapter are copied; no
narrative runtime, Dialogue Manager, addon installation, scenes or assets. The
seeded capture deliberately contains an expectation failure at zero-based step 6.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(godot: str, project: Path, env: dict[str, str], script: str,
        arguments: list[str] | None = None, expect_success: bool = True) -> str:
    command = [godot, '--headless', '--path', str(project), '--script', f'res://{script}']
    if arguments:
        command += ['--', *arguments]
    result = subprocess.run(command, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, timeout=60)
    if 'SCRIPT ERROR:' in result.stdout or '\nERROR:' in result.stdout:
        raise AssertionError(f'Godot script error:\n{result.stdout}')
    if (result.returncode == 0) != expect_success:
        raise AssertionError(f'Unexpected replay exit {result.returncode}:\n{result.stdout}')
    for line in result.stdout.splitlines():
        if line.startswith('Replay '):
            print(f'{project.name}: {line}')
    return result.stdout


def check(godot: str = 'godot') -> None:
    executable = shutil.which(godot)
    if executable is None:
        raise SystemExit(f'Godot executable not found: {godot}; use --godot PATH')
    with tempfile.TemporaryDirectory(prefix='foundation-replay-') as temporary:
        base = Path(temporary)
        environment = os.environ.copy()
        for name in ('XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
            path = base / name.lower()
            path.mkdir()
            environment[name] = str(path)
        project = base / 'standalone'
        project.mkdir()
        (project / 'project.godot').write_text(
            'config_version=5\n[application]\nconfig/name="Standalone replay fixture"\n'
            '[rendering]\nrenderer/rendering_method="gl_compatibility"\n', encoding='utf-8')
        files = {
            'replay_record.gd': 'addons/story_foundation/testing/replay_record.gd',
            'replay_record.gd.uid': 'addons/story_foundation/testing/replay_record.gd.uid',
            'test_replay.gd': 'tests/regression/test_replay.gd',
            'seeded_replay.gd': 'examples/replay/seeded_replay.gd',
        }
        for name, source in files.items():
            shutil.copyfile(ROOT / source, project / name)
        assert {file.name for file in project.iterdir()} == set(files) | {'project.godot'}
        run(executable, project, environment, 'test_replay.gd')
        record = base / 'captured.json'
        repeat = base / 'captured-again.json'
        run(executable, project, environment, 'seeded_replay.gd', ['--capture', str(record)])
        run(executable, project, environment, 'seeded_replay.gd', ['--capture', str(repeat)])
        assert record.read_bytes() == repeat.read_bytes(), 'Same seed did not produce identical record bytes'
        payload = json.loads(record.read_text(encoding='utf-8'))
        assert payload['seed'] == 73491 and len(payload['steps']) == 7
        assert payload['steps'][6]['expectation']['ok'] is False
        assert all(step['expectation']['ok'] for step in payload['steps'][:6])
        run(executable, project, environment, 'seeded_replay.gd', ['--replay', str(record)])
        relocated = base / 'relocated'
        relocated.mkdir()
        for name in set(files) | {'project.godot'}:
            shutil.copyfile(project / name, relocated / name)
        shutil.rmtree(project)
        assert not (relocated / '.godot').exists()
        run(executable, relocated, environment, 'test_replay.gd')
        run(executable, relocated, environment, 'seeded_replay.gd', ['--replay', str(record)])
        bad = json.loads(record.read_text(encoding='utf-8'))
        bad['identity']['build'] = '0' * 64
        mismatch = base / 'identity-mismatch.json'
        mismatch.write_text(json.dumps(bad), encoding='utf-8')
        output = run(executable, relocated, environment, 'seeded_replay.gd',
                     ['--replay', str(mismatch)], expect_success=False)
        assert 'replay identity mismatch' in output
    print('Optional replay helper passed standalone capture, strict verification and fresh relocation')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot', default='godot')
    check(parser.parse_args().godot)
