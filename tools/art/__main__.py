"""Independent offline character-art entry point (Python standard library only)."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from .manifest import ArtError
from .characters.pipeline import build


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('validate', 'build'):
        p = sub.add_parser(name)
        p.add_argument('manifest', type=Path)
        if name == 'build': p.add_argument('--output', required=True, type=Path)
        p.add_argument('--aseprite', help='Optional Aseprite 1.3 executable; required only for native Aseprite input')
        p.add_argument('--godot', action='store_true', help='Also emit relocatable Godot SpriteFrames + preview scene')
        p.add_argument('--allow-unknown-provenance', action='store_true', help='Exploratory override; records unresolved rights warning')
    args = parser.parse_args()
    try:
        report = build(args.manifest, getattr(args, 'output', None), aseprite=args.aseprite,
                       allow_unknown_provenance=args.allow_unknown_provenance, godot=args.godot)
    except (ArtError, OSError, KeyError, TypeError, ValueError) as error:
        print(f'Art pipeline failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
