#!/usr/bin/env python3
"""Rebuild the original MIT geometry fixtures, not a general character generator.

No game art/reference images/AI prompts are used. Deliberately different authored
silhouettes, cell sizes, palettes, animation counts/timing and pivots exercise the
same pipeline. Real character anatomy/poses/masks remain artist-owned.
"""
from pathlib import Path
import hashlib
import json
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.art.png import encode


def create(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    fixtures = [
        ('narrow', [8, 12], [4, 11], 2, ['#00000000', '#293148ff', '#d79544ff'],
         [('idle_down', [160, 240], True)],
         [['...11...', '..1111..', '...22...', '...22...', '...22...', '...22...', '...22...', '..1..1..', '..1..1..', '..1..1..', '.11..11.', '........'],
          ['...11...', '..1111..', '...22...', '...22...', '...22...', '...22...', '...22...', '..1..1..', '.1....1.', '.1....1.', '.11..11.', '........']]),
        ('broad', [12, 12], [6, 11], 3, ['#00000000', '#243d47ff', '#5d9091ff', '#d5b582ff'],
         [('work_down', [90, 130, 210], False)],
         [['....1111....', '....1331....', '..12222221..', '..12222221..', '..12222221..', '..12222221..', '...111111...', '...11..11...', '...11..11...', '...11..11...', '..111..111..', '............'],
          ['....1111....', '....1331....', '.112222221..', '.112222221..', '..12222221..', '..12222221..', '...111111...', '...11..11...', '...11..11...', '...11..11...', '..111..111..', '............'],
          ['....1111....', '....1331....', '..122222211.', '..122222211.', '..12222221..', '..12222221..', '...111111...', '...11..11...', '...11..11...', '...11..11...', '..111..111..', '............']]),
    ]
    for name, cell, pivot, columns, palette, states, drawings in fixtures:
        pixels = bytearray()
        for y in range(cell[1]):
            for drawing in drawings:
                assert len(drawing) == cell[1] and len(drawing[y]) == cell[0]
                for c in drawing[y]: pixels += bytes.fromhex(palette[0 if c == '.' else int(c)][1:])
        data = encode(cell[0] * columns, cell[1], pixels)
        (directory / f'{name}.png').write_bytes(data)
        tags, start = [], 0
        for state, durations, loop in states:
            tags.append({'name': state, 'start': start, 'count': len(durations), 'durations_ms': durations, 'loop': loop})
            start += len(durations)
        manifest = {'schema_version': 1, 'asset_id': f'fixture_{name}', 'kind': 'character_sprite',
                    'source': {'adapter': 'png', 'path': f'{name}.png', 'sha256': hashlib.sha256(data).hexdigest()},
                    'provenance': {'origin': 'original', 'creator': 'Foundation contributors', 'license': 'MIT',
                                   'rights': 'recorded', 'notes': 'Original synthetic geometry fixture; see repository LICENSE. No game character art.'},
                    'cell': cell, 'pivot': pivot, 'columns': columns, 'palette': palette, 'hard_alpha': True, 'tags': tags}
        (directory / f'{name}.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__': create(Path(__file__).parent)
