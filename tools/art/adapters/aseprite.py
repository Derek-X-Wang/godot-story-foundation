"""Optional read-only Aseprite 1.3 CLI/Lua adapter. Never invokes game scripts."""
from __future__ import annotations
from pathlib import Path
import subprocess
from ..manifest import ArtError, read_json, require
from ..characters.contract import frame_durations


def run(command: list[str]) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=True)
    except (OSError, subprocess.SubprocessError) as error:
        detail = getattr(error, 'stderr', '') or str(error)
        raise ArtError(f'Aseprite adapter failed: {detail[:2000]}') from error
    # Some Lua errors have historically returned exit 0. Outputs are also checked.
    require('error:' not in result.stderr.lower(), f'Aseprite error: {result.stderr[:2000]}')
    return result.stdout.strip()


def export(source: Path, m: dict, scratch: Path, executable: str) -> tuple[Path, dict]:
    version = run([executable, '--version'])
    require('Aseprite 1.3.' in version, 'Aseprite adapter requires 1.3.x; this version has not been validated')
    inspect = scratch / 'native.json'
    run([executable, '--batch', '--script-param', f'source={source}', '--script-param', f'output={inspect}',
         '--script', str(Path(__file__).with_name('inspect_aseprite.lua'))])
    native = read_json(inspect)
    require(native['cell'] == m['cell'], 'native cell differs from manifest')
    require(native['durations_ms'] == frame_durations(m), 'native frame durations/count differ from manifest')
    if 'layers' in m['source']:
        require(native['layers'] == m['source']['layers'], 'native layer names/order differ from manifest')
    if native['color_mode'] == 'indexed':
        for colors in native['palettes']:
            require(colors == m['palette'], 'native indexed palette differs from manifest (including unused colors/order)')
    png, metadata = scratch / 'raw.png', scratch / 'raw.json'
    run([executable, '--batch', '--list-tags', '--list-layers', '--list-slices', str(source),
         '--sheet-type', 'rows', '--sheet-columns', str(m['columns']), '--filename-format', '{frame}',
         '--format', 'json-array', '--data', str(metadata), '--sheet', str(png)])
    data = read_json(metadata)
    expected_tags = [{'name': t['name'], 'from': t['start'], 'to': t['start'] + t['count'] - 1, 'direction': 'forward'} for t in m['tags']]
    actual_tags = [{k: t.get(k) for k in ('name', 'from', 'to', 'direction')} for t in data['meta']['frameTags']]
    require(actual_tags == expected_tags, 'native tags/ranges/direction differ from manifest; v1 supports forward tags only')
    frames = data['frames']
    durations = frame_durations(m)
    require(len(frames) == len(durations), 'Aseprite export frame count mismatch')
    w, h = m['cell']
    for i, frame in enumerate(frames):
        require(frame['frame'] == {'x': i % m['columns'] * w, 'y': i // m['columns'] * h, 'w': w, 'h': h}
                and not frame['rotated'] and not frame['trimmed']
                and frame['sourceSize'] == {'w': w, 'h': h}
                and frame['duration'] == durations[i], 'Aseprite export grid/trim/rotation/timing mismatch')
    if 'pivot_slice' in m['source']:
        slices = [s for s in data['meta']['slices'] if s['name'] == m['source']['pivot_slice']]
        require(len(slices) == 1 and len(slices[0]['keys']) == 1, 'expected a single constant native pivot slice')
        key = slices[0]['keys'][0]
        require(key['frame'] == 0 and key['bounds'] == {'x': 0, 'y': 0, 'w': w, 'h': h}
                and key.get('pivot') == dict(zip(('x', 'y'), m['pivot'])), 'native pivot slice mismatch')
    return png, {'adapter': 'aseprite', 'tool_version': version, 'native': native}
