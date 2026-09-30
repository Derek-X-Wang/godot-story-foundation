#!/usr/bin/env python3
"""Verify and import the actual addon ZIP in a fresh disposable project."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import zipfile
from fetch_dependencies import safe_zip_members, copy_member

ROOT = Path(__file__).resolve().parents[1]


def check(godot: str = 'godot') -> None:
    version = (ROOT / 'VERSION').read_text().strip()
    archive_path = ROOT / '.build/releases' / f'godot-story-foundation-v{version}.zip'
    project = ROOT / '.build/release-smoke'
    if project.exists():
        shutil.rmtree(project)
    shutil.copytree(ROOT / '.build/village', project,
                    ignore=shutil.ignore_patterns('addons', '.godot'))
    with zipfile.ZipFile(archive_path) as archive:
        members = safe_zip_members(archive, 16 * 1024 * 1024)
        manifest = json.loads(archive.read('PACKAGE-MANIFEST.json'))
        expected = set(manifest['files']) | {'PACKAGE-MANIFEST.json'}
        if set(archive.namelist()) != expected:
            raise ValueError('Package membership differs from its manifest')
        for name, digest in manifest['files'].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError(f'Package member failed checksum: {name}')
        for info, path in members:
            if not info.is_dir():
                copy_member(archive, info, project.joinpath(*path.parts))
    commands = [
        ['--editor', '--import'],
        ['--script', 'res://tests/runtime/run.gd'],
        ['--script', 'res://tests/runtime/test_dialogue.gd'],
        ['--quit-after', '5'],
    ]
    for index, arguments in enumerate(commands):
        result = subprocess.run([godot, '--headless', '--path', str(project), *arguments],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
        (ROOT / '.build' / f'release-smoke-{index}.log').write_text(result.stdout)
        if result.returncode or 'SCRIPT ERROR:' in result.stdout or '\nERROR:' in result.stdout:
            print(result.stdout)
            raise SystemExit(result.returncode or 1)
    print('Release ZIP manifest, fresh import, runtime, dialogue and main-scene smoke checks passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot', default='godot')
    check(parser.parse_args().godot)
