#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
"""Package only the optional scene scripts, UIDs and first-party MIT license.

No downloaded dependency, narrative runtime, game fixture or asset is included.
The deterministic manifest hashes every payload file; record the source commit
and archive SHA-256 in the consuming game's own dependency lock.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from package_release import deterministic_zip

ROOT = Path(__file__).resolve().parents[1]
SCENE_API_VERSION = 1
MEMBERS = (
    'LICENSE',
    'addons/story_foundation/scene/depth_order.gd',
    'addons/story_foundation/scene/depth_order.gd.uid',
    'addons/story_foundation/scene/rect_navigation.gd',
    'addons/story_foundation/scene/rect_navigation.gd.uid',
)


def package(output: Path) -> Path:
    files: dict[str, bytes] = {}
    for name in MEMBERS:
        path = ROOT / name
        if path.is_symlink() or path.resolve() != path.absolute() or not path.is_file():
            raise ValueError(f'Not a regular scene package source: {name}')
        files[name] = path.read_bytes()
    manifest = {
        'package_kind': 'optional-scene-primitives',
        'scene_api_version': SCENE_API_VERSION,
        'files': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
    }
    files['SCENE-MANIFEST.json'] = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    target = output / f'godot-story-foundation-scene-api{SCENE_API_VERSION}.zip'
    deterministic_zip(files, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_suffix('.zip.sha256').write_text(f'{digest}  {target.name}\n', encoding='utf-8')
    print(f'{target.name}: {len(files)} files, SHA256 {digest}')
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.build/releases')
    package(parser.parse_args().output)
