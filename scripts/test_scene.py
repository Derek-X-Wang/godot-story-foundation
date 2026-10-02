#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
"""Test each optional scene primitive in its own fresh, relocated Godot project.

No narrative runtime, art pipeline, Dialogue Manager, autoload, asset or existing
Godot import cache is copied. Python 3.11+ standard library and Godot 4.6.3 only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

from package_scene import MEMBERS, package

ROOT = Path(__file__).resolve().parents[1]
SELECTED = {'rect_navigation': 'test_rect_navigation', 'depth_order': 'test_depth_order'}


def run(godot: str, project: Path, environment: dict[str, str], arguments: list[str]) -> str:
    result = subprocess.run([godot, '--headless', '--path', str(project), *arguments],
                            env=environment, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, timeout=120)
    if result.returncode or 'SCRIPT ERROR:' in result.stdout or '\nERROR:' in result.stdout:
        raise RuntimeError(f'Godot check failed ({project.name}):\n{result.stdout}')
    for line in result.stdout.splitlines():
        if line.startswith('Scene '):
            print(f'{project.name}: {line}')
    return result.stdout


def check(godot: str = 'godot') -> None:
    if shutil.which(godot) is None:
        raise SystemExit(f'Godot executable not found: {godot}; use --godot PATH.')
    with tempfile.TemporaryDirectory(prefix='foundation-scene-') as temporary:
        base = Path(temporary)
        environment = os.environ.copy()
        for key in ('XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
            destination = base / key.lower()
            destination.mkdir()
            environment[key] = str(destination)
        archive = package(base / 'package')
        repeat = package(base / 'repeat')
        assert archive.read_bytes() == repeat.read_bytes(), 'Scene archive is not deterministic'
        with zipfile.ZipFile(archive) as bundle:
            assert set(bundle.namelist()) == set(MEMBERS) | {'SCENE-MANIFEST.json'}
            manifest = json.loads(bundle.read('SCENE-MANIFEST.json'))
            assert set(manifest['files']) == set(MEMBERS)
            for name, digest in manifest['files'].items():
                assert hashlib.sha256(bundle.read(name)).hexdigest() == digest
            payload = {name: bundle.read(name) for name in MEMBERS}
        for module, test in SELECTED.items():
            project = base / module
            project.mkdir()
            (project / 'project.godot').write_text(
                'config_version=5\n[application]\nconfig/name="Isolated scene primitive"\n'
                '[rendering]\nrenderer/rendering_method="gl_compatibility"\n', encoding='utf-8')
            for suffix in ('.gd', '.gd.uid'):
                (project / f'selected{suffix}').write_bytes(payload[f'addons/story_foundation/scene/{module}{suffix}'])
            shutil.copyfile(ROOT / f'tests/scene/{test}.gd', project / 'run.gd')
            assert {path.name for path in project.iterdir()} == {'project.godot', 'selected.gd', 'selected.gd.uid', 'run.gd'}
            run(godot, project, environment, ['--editor', '--import'])
            run(godot, project, environment, ['--script', 'res://run.gd'])
            relocated = base / f'{module}-relocated'
            relocated.mkdir()
            for name in ('project.godot', 'selected.gd', 'selected.gd.uid', 'run.gd'):
                shutil.copyfile(project / name, relocated / name)
            shutil.rmtree(project)
            run(godot, relocated, environment, ['--editor', '--import'])
            run(godot, relocated, environment, ['--script', 'res://run.gd'])
    print('Optional scene primitives passed independently, including fresh relocation')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot', default='godot')
    check(parser.parse_args().godot)
