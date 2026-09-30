#!/usr/bin/env python3
"""Build an allowlisted deterministic addon ZIP and content hash manifest."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'.git', '.godot', '__pycache__', '.DS_Store'}


def collect_tree(source: Path, prefix: str) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    if source.is_symlink() or source.resolve() != source.absolute():
        raise ValueError('Symlinked package source or ancestor is not allowed')
    if not source.is_dir():
        raise ValueError(f'Missing package source: {source.name}')
    for path in sorted(source.rglob('*')):
        rel = path.relative_to(source)
        if any(part in EXCLUDED for part in rel.parts):
            continue
        if path.is_symlink():
            raise ValueError(f'Symlink not allowed in package: {rel}')
        # Preserve upstream .import text metadata: the plugin's first editor
        # load needs its asset UIDs before the normal asset scan finishes.
        if path.is_file() and path.suffix not in {'.pyc', '.log', '.tmp'}:
            files[f'{prefix}/{rel.as_posix()}'] = path.read_bytes()
    return files


def deterministic_zip(files: dict[str, bytes], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, contents in sorted(files.items()):
            parts = Path(name).parts
            if not name or name.startswith('/') or '..' in parts or '\\' in name:
                raise ValueError('Unsafe archive member')
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(info, contents)


def package(output: Path) -> Path:
    version = (ROOT / 'VERSION').read_text().strip()
    files = collect_tree(ROOT / 'addons/story_foundation', 'addons/story_foundation')
    files.update(collect_tree(ROOT / '.deps/dialogue_manager', 'addons/dialogue_manager'))
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'deps.lock.json', 'VERSION'):
        path = ROOT / name
        if path.is_symlink() or path.resolve().parent != ROOT:
            raise ValueError('Unsafe top-level package file')
        files[name] = path.read_bytes()
    files.update(collect_tree(ROOT / 'licenses', 'licenses'))
    files['INSTALL.md'] = (
        '# Godot Story Foundation addon bundle\n\n'
        f'Foundation {version}. Unzip into a Godot 4.6.3 project root.\n'
        'This installs addons/story_foundation and the pinned official Dialogue Manager.\n'
        'Enable Dialogue Manager in Project Settings > Plugins to install its importer\n'
        'and autoload. The foundation runtime itself needs no editor plugin.\n'
        'Keep your gameplay code and approved content outside addon directories.\n'
        'Save this bundle SHA-256 and the source release tag/commit in your game manifest.\n'
        'See the repository README and docs/versioning.md for setup and upgrade tests.\n'
        'Third-party code retains its original license.\n'
    ).encode()
    manifest = {
        'foundation_version': version,
        'package_kind': 'runtime-addons',
        'files': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
    }
    files['PACKAGE-MANIFEST.json'] = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    target = output / f'godot-story-foundation-v{version}.zip'
    deterministic_zip(files, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    (target.with_suffix('.zip.sha256')).write_text(f'{digest}  {target.name}\n')
    print(f'{target.name}: {len(files)} files, {target.stat().st_size} bytes, SHA256 {digest}')
    return target


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.build/releases')
    args = parser.parse_args()
    package(args.output)
