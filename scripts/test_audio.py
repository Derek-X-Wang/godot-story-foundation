#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
"""Test each optional audio primitive in its own fresh, relocated Godot project.

No narrative runtime, scene primitive, art pipeline, Dialogue Manager, autoload,
audio asset, UID sidecar or existing import cache is copied. Python 3.11+ standard
library and Godot 4.6.3 only. These are native tests, not browser/audio-device tests.
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

from package_audio import AUDIO_API_VERSION, MEMBERS, package

ROOT = Path(__file__).resolve().parents[1]
SELECTED = {
    'web_safe_audio_buses': 'test_web_safe_audio_buses',
    'audio_bus_settings': 'test_audio_bus_settings',
    'gain_envelope': 'test_gain_envelope',
}
PROJECT_FILES = ('project.godot', 'selected.gd', 'run.gd')


def run(godot: str, project: Path, environment: dict[str, str], arguments: list[str]) -> str:
    result = subprocess.run([godot, '--headless', '--path', str(project), *arguments],
                            env=environment, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, timeout=120)
    lines = result.stdout.splitlines()
    if result.returncode or any(line.lstrip().startswith(('SCRIPT ERROR:', 'ERROR:')) for line in lines):
        raise RuntimeError(f'Godot check failed ({project.name}):\n{result.stdout}')
    reports = [line for line in lines if line.startswith('Audio ')]
    if '--script' in arguments and not reports:
        raise RuntimeError(f'Godot audio test reported no result ({project.name}):\n{result.stdout}')
    for line in reports:
        print(f'{project.name}: {line}')
    return result.stdout


def check(godot: str = 'godot') -> None:
    executable = shutil.which(godot)
    if executable is None:
        raise SystemExit(f'Godot executable not found: {godot}; use --godot PATH.')
    with tempfile.TemporaryDirectory(prefix='foundation-audio-') as temporary:
        base = Path(temporary)
        environment = os.environ.copy()
        for key in ('XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
            destination = base / key.lower()
            destination.mkdir()
            environment[key] = str(destination)
        archive = package(base / 'package')
        repeat = package(base / 'repeat')
        assert archive.read_bytes() == repeat.read_bytes(), 'Audio archive is not deterministic'
        with zipfile.ZipFile(archive) as bundle:
            assert len(bundle.namelist()) == len(MEMBERS) + 1
            assert set(bundle.namelist()) == set(MEMBERS) | {'AUDIO-MANIFEST.json'}
            manifest = json.loads(bundle.read('AUDIO-MANIFEST.json'))
            assert manifest['package_kind'] == 'optional-audio-primitives'
            assert manifest['audio_api_version'] == AUDIO_API_VERSION
            assert set(manifest['files']) == set(MEMBERS)
            for name, digest in manifest['files'].items():
                assert hashlib.sha256(bundle.read(name)).hexdigest() == digest
            payload = {name: bundle.read(name) for name in MEMBERS}
        for module, test in SELECTED.items():
            project = base / module
            project.mkdir()
            (project / 'project.godot').write_text(
                'config_version=5\n[application]\nconfig/name="Isolated audio primitive"\n'
                '[rendering]\nrenderer/rendering_method="gl_compatibility"\n', encoding='utf-8')
            (project / 'selected.gd').write_bytes(payload[f'addons/story_foundation/audio/{module}.gd'])
            shutil.copyfile(ROOT / f'tests/audio/{test}.gd', project / 'run.gd')
            assert {path.name for path in project.iterdir()} == set(PROJECT_FILES)
            run(executable, project, environment, ['--editor', '--import'])
            run(executable, project, environment, ['--script', 'res://run.gd'])
            relocated = base / f'{module}-relocated'
            relocated.mkdir()
            for name in PROJECT_FILES:
                shutil.copyfile(project / name, relocated / name)
            shutil.rmtree(project)
            assert not project.exists()
            assert {path.name for path in relocated.iterdir()} == set(PROJECT_FILES)
            run(executable, relocated, environment, ['--editor', '--import'])
            run(executable, relocated, environment, ['--script', 'res://run.gd'])
    print('Optional audio primitives passed independently, including fresh relocation')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot', default='godot')
    check(parser.parse_args().godot)
