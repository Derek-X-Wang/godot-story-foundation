#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
"""Verify optional character resources in two fresh, isolated Godot projects.

Only the Python standard library and Godot are required. Tiny original fixtures
are generated in temporary directories; no narrative runtime, dialogue addon,
public asset download, or pre-existing import cache participates in this test.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('art_godot_adapter', ROOT / 'tools/art/adapters/godot.py')
assert SPEC is not None and SPEC.loader is not None
ADAPTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADAPTER)


def _png(width: int, height: int, pixels: list[list[int]]) -> bytes:
    """Encode an original 8-bit RGBA PNG using only the standard library."""
    def chunk(kind: bytes, value: bytes) -> bytes:
        return (struct.pack('>I', len(value)) + kind + value
                + struct.pack('>I', zlib.crc32(kind + value) & 0xffffffff))

    rows = b''.join(b'\x00' + bytes(component for pixel in pixels[y * width:(y + 1) * width]
                                    for component in pixel) for y in range(height))
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def create_fixture(directory: Path, cell: tuple[int, int], pivot: tuple[int, int], asset_id: str) -> None:
    directory.mkdir(parents=True)
    columns = 3
    width, height = cell[0] * columns, cell[1] * 2
    pixels = [[0, 0, 0, 0] for _ in range(width * height)]
    durations = [40, 90, 130, 70, 20, 110]
    frames = []
    for index, duration in enumerate(durations):
        left, top = (index % columns) * cell[0], (index // columns) * cell[1]
        frames.append({'rect': [left, top, *cell], 'duration_ms': duration})
        for y in range(cell[1]):
            for x in range(cell[0]):
                # Unequal, non-square cells and asymmetric content catch transposed
                # regions, unwanted resizing, dropped alpha, and frame reordering.
                alpha = 0 if x == 0 and y == 0 else (128 if x == 1 and y == 1 else 255)
                pixels[(top + y) * width + left + x] = [
                    (31 + index * 37 + x * 9) % 256,
                    (53 + index * 19 + y * 13) % 256,
                    (97 + index * 23 + x * 5 + y * 7) % 256,
                    alpha,
                ]
    atlas = {
        'schema_version': 1, 'kind': 'character_sprite', 'asset_id': asset_id,
        'cell': list(cell), 'pivot': list(pivot), 'columns': columns, 'frames': frames,
        'tags': [
            {'name': 'idle', 'start': 0, 'count': 3, 'durations_ms': durations[:3], 'loop': True},
            {'name': 'wave', 'start': 3, 'count': 3, 'durations_ms': durations[3:], 'loop': False},
        ],
    }
    manifest = {key: atlas[key] for key in ('asset_id', 'cell', 'pivot', 'tags')}
    png = _png(width, height, pixels)
    (directory / 'atlas.png').write_bytes(png)
    (directory / 'atlas.json').write_text(json.dumps(atlas), encoding='utf-8')
    expected = {'asset_id': asset_id, 'width': width, 'height': height, 'pixels': pixels}
    (directory / 'expected.json').write_text(json.dumps(expected), encoding='utf-8')
    before = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
              for name in ('atlas.png', 'atlas.json')}
    ADAPTER.write_godot(directory, manifest, atlas)
    first = {name: (directory / name).read_bytes() for name in ('sprite_frames.tres', 'preview.tscn')}
    ADAPTER.write_godot(directory, manifest, atlas)
    for name, original in first.items():
        if original != (directory / name).read_bytes():
            raise AssertionError(f'Non-deterministic Godot output: {name}')
        if b'res://' in original or str(directory).encode() in original:
            raise AssertionError(f'Non-relocatable resource path: {name}')
    for name, digest in before.items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != digest:
            raise AssertionError(f'Adapter changed portable source: {name}')


def prepare_project(directory: Path, fixture_paths: list[str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'project.godot').write_text('''; Isolated optional-art consumer fixture.
config_version=5

[application]
config/name="Character adapter smoke test"

[rendering]
renderer/rendering_method="gl_compatibility"
''', encoding='utf-8')
    (directory / 'fixture_paths.json').write_text(json.dumps(fixture_paths), encoding='utf-8')
    shutil.copyfile(ROOT / 'tests/art_godot/run.gd', directory / 'run.gd')


def create_public_fixture(directory: Path, name: str) -> None:
    """Exercise the public PNG-to-Godot CLI as well as the isolated serializer."""
    manifest_path = ROOT / 'examples/art/characters' / f'{name}.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    source = manifest_path.parent / manifest['source']['path']
    before = source.read_bytes()
    result = subprocess.run(
        [sys.executable, '-m', 'tools.art', 'build', str(manifest_path),
         '--output', str(directory), '--godot'], cwd=ROOT,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=30,
    )
    if result.returncode:
        raise RuntimeError(f'Public character build failed ({name}):\n{result.stdout}')
    if source.read_bytes() != before:
        raise AssertionError(f'Build changed original public source: {name}')
    # This reader is the portable art codec, independent of any Godot resource.
    sys.path.insert(0, str(ROOT))
    try:
        from tools.art.png import decode
        width, height, rgba = decode(before)
    finally:
        sys.path.pop(0)
    expected = {'asset_id': manifest['asset_id'], 'width': width, 'height': height,
                'pixels': [list(rgba[index:index + 4]) for index in range(0, len(rgba), 4)]}
    (directory / 'expected.json').write_text(json.dumps(expected), encoding='utf-8')


def run_godot(godot: str, project: Path, environment: dict[str, str], arguments: list[str]) -> None:
    result = subprocess.run([godot, '--headless', '--path', str(project), *arguments],
                            env=environment, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, timeout=120)
    if result.returncode or 'SCRIPT ERROR:' in result.stdout or '\nERROR:' in result.stdout:
        raise RuntimeError(f'Godot check failed ({project.name}):\n{result.stdout}')
    for line in result.stdout.splitlines():
        if line.startswith('Art Godot consumer:'):
            print(f'{project.name}: {line}')


def check(godot: str = 'godot') -> None:
    if shutil.which(godot) is None:
        raise SystemExit(f'Godot executable not found: {godot}. Install Godot 4.6.3 or use --godot PATH.')
    with tempfile.TemporaryDirectory(prefix='foundation-art-godot-') as temporary:
        base = Path(temporary)
        environment = os.environ.copy()
        for key in ('XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME'):
            destination = base / key.lower()
            destination.mkdir()
            environment[key] = str(destination)
        source = base / 'original-project'
        names = ('narrow', 'broad', 'public_narrow', 'public_broad')
        fixture_paths = [f'res://assets/{name}' for name in names]
        prepare_project(source, fixture_paths)
        create_fixture(source / 'assets/narrow', (3, 5), (1, 4), 'narrow')
        # The main pipeline validates asset IDs, but the serialization boundary
        # must still quote any supplied resource name safely.
        create_fixture(source / 'assets/broad', (8, 4), (2, 3), 'broad "quoted" \\ name\nfixture')
        for name in ('narrow', 'broad'):
            create_public_fixture(source / 'assets' / f'public_{name}', name)
        run_godot(godot, source, environment, ['--editor', '--import'])
        run_godot(godot, source, environment, ['--fixed-fps', '1000', '--script', 'res://run.gd'])

        relocated = base / 'relocated-project'
        paths = [f'res://game/characters/moved bundle/{name}' for name in names]
        prepare_project(relocated, paths)
        for name in names:
            destination = relocated / 'game/characters/moved bundle' / name
            destination.mkdir(parents=True)
            for filename in ('atlas.png', 'atlas.json', 'sprite_frames.tres', 'preview.tscn', 'expected.json'):
                shutil.copyfile(source / 'assets' / name / filename, destination / filename)
        # Prove neither the old project nor its imports can satisfy a reference.
        shutil.rmtree(source)
        run_godot(godot, relocated, environment, ['--editor', '--import'])
        run_godot(godot, relocated, environment, ['--fixed-fps', '1000', '--script', 'res://run.gd'])
    print('Optional Godot art import, pixels, geometry, timing, preview playback and relocation passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot', default='godot')
    check(parser.parse_args().godot)
