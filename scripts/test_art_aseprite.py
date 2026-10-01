#!/usr/bin/env python3
"""Opt-in real Aseprite CLI/Lua substitution test; never installs the editor."""
from pathlib import Path
import argparse
import copy
import json
import subprocess
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.art.characters.pipeline import build
from tools.art.manifest import ArtError, canonical, digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aseprite', required=True)
    args = parser.parse_args()
    checks = 0
    with tempfile.TemporaryDirectory(prefix='foundation-aseprite-') as name:
        root = Path(name)
        for fixture, indexed in (('narrow', False), ('broad', False), ('narrow', True)):
            manifest_path = ROOT / f'examples/art/characters/{fixture}.json'
            m = json.loads(manifest_path.read_text())
            suffix = fixture + ('-indexed' if indexed else '')
            source = root / f'{suffix}.aseprite'
            authored_manifest = root / f'{suffix}-authored.json'
            if indexed: m['palette'].append('#ffff00ff')  # Deliberately unused authored color.
            authored_manifest.write_bytes(canonical(m))
            subprocess.run([args.aseprite, '--batch', '--script-param', f'manifest={authored_manifest}',
                            '--script-param', f'png={manifest_path.with_suffix(".png")}', '--script-param', f'output={source}',
                            '--script-param', f'indexed={str(indexed).lower()}',
                            '--script', str(ROOT / 'tests/art_godot/create_native_fixture.lua')], check=True)
            original = digest(source)
            m['source'] = {'adapter': 'aseprite', 'path': source.name, 'sha256': original,
                           'layers': ['Authored pixels'], 'pivot_slice': 'cell'}
            native_manifest = root / f'{suffix}.json'
            native_manifest.write_bytes(canonical(m))
            png_out, native_out, again = root / f'{suffix}-png', root / f'{suffix}-native', root / f'{suffix}-again'
            build(manifest_path, png_out, godot=True)
            build(native_manifest, native_out, aseprite=args.aseprite, godot=True)
            build(native_manifest, again, aseprite=args.aseprite, godot=True)
            for artifact in ('atlas.png', 'atlas.json', 'sprite_frames.tres', 'preview.tscn'):
                assert (png_out / artifact).read_bytes() == (native_out / artifact).read_bytes(), artifact
                checks += 1
            for artifact in native_out.iterdir():
                assert artifact.read_bytes() == (again / artifact.name).read_bytes(), artifact
                checks += 1
            assert digest(source) == original
            checks += 1
            for changed in ('duration', 'tag', 'pivot', 'layers', 'cell') + (('palette_order', 'unused_color') if indexed else ()):
                bad = copy.deepcopy(m)
                if changed == 'duration': bad['tags'][0]['durations_ms'][0] += 1
                elif changed == 'tag': bad['tags'][0]['name'] = 'wrong'
                elif changed == 'pivot': bad['pivot'][0] -= 1
                elif changed == 'layers': bad['source']['layers'] = ['Wrong layer']
                elif changed == 'palette_order': bad['palette'][1], bad['palette'][2] = bad['palette'][2], bad['palette'][1]
                elif changed == 'unused_color': bad['palette'][-1] = '#ff00ffff'
                else: bad['cell'][0] += 1
                native_manifest.write_bytes(canonical(bad))
                try: build(native_manifest, aseprite=args.aseprite)
                except ArtError: checks += 1
                else: raise AssertionError(f'missed native {changed} mismatch')
    print(f'Aseprite adapter: {checks} checks passed; two authored fixtures plus indexed variant, PNG/native parity, deterministic output, source preservation, rejection paths')


if __name__ == '__main__': main()
