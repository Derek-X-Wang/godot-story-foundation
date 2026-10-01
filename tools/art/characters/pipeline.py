"""Bounded pixel-sprite normalization, validation and transactional publication."""
from __future__ import annotations
import hashlib
from pathlib import Path
import tempfile
from ..manifest import canonical, digest, read_json, require, source_path
from .. import png
from .contract import frame_durations, validate_manifest


def prepare(manifest_path: Path, work: Path, *, aseprite: str | None = None,
            allow_unknown_provenance: bool = False, godot: bool = False) -> dict:
    m = read_json(manifest_path)
    warnings = validate_manifest(m, allow_unknown_provenance)
    source = source_path(manifest_path, m['source'])
    original_hash = digest(source)
    info = {'adapter': 'png', 'tool_version': 'foundation-png-v1'}
    if m['source']['adapter'] == 'aseprite':
        require(bool(aseprite), 'Aseprite input requires --aseprite /path/to/aseprite; PNG input needs no editor')
        from ..adapters.aseprite import export
        input_png, info = export(source, m, work, aseprite)
    else:
        input_png = source
    width, height, pixels = png.decode(input_png.read_bytes())
    w, h = m['cell']
    durations = frame_durations(m)
    columns = m['columns']
    rows = (len(durations) + columns - 1) // columns
    require((width, height) == (w * columns, h * rows), 'source sheet dimensions do not match declared grid/frame count')
    palette = {bytes.fromhex(color[1:]) for color in m['palette']}
    occupied, colors = [False] * len(durations), set()
    for index in range(width * height):
        pixel = pixels[index * 4:index * 4 + 4]
        require(pixel[3] in (0, 255), 'hard alpha violated: semi-transparent pixel')
        require(pixel in palette, f'pixel color #{pixel.hex()} is absent from palette')
        frame = (index // width // h) * columns + index % width // w
        if pixel[3]:
            require(frame < len(durations), 'nonempty padding cell outside declared frames')
            occupied[frame] = True
        colors.add(pixel)
    require(all(occupied), 'empty frame: every declared sprite frame must contain visible pixels')
    require(digest(source) == original_hash, 'source changed during export; no output promoted')
    atlas = {'schema_version': 1, 'asset_id': m['asset_id'], 'kind': m['kind'], 'cell': m['cell'],
             'pivot': m['pivot'], 'columns': columns,
             'frames': [{'rect': [i % columns * w, i // columns * h, w, h], 'duration_ms': d} for i, d in enumerate(durations)],
             'tags': m['tags']}
    (work / 'atlas.png').write_bytes(png.encode(width, height, pixels))
    (work / 'atlas.json').write_bytes(canonical(atlas))
    if godot:
        from ..adapters.godot import write_godot
        write_godot(work, m, atlas)
    artifacts = {p.name: digest(p) for p in sorted(work.iterdir()) if p.name in ('atlas.png', 'atlas.json', 'sprite_frames.tres', 'preview.tscn')}
    report = {'schema_version': 1, 'pipeline': 'character_sprite_v1', 'asset_id': m['asset_id'],
              'manifest_sha256': hashlib.sha256(canonical(m)).hexdigest(), 'source_sha256': original_hash,
              'source_preserved': True, 'provenance': m['provenance'], 'warnings': warnings,
              'rights_clearance': 'not_determined_by_tool', 'adapter': info,
              'checks': {'hard_alpha': True, 'palette': True, 'grid': True, 'tags_timing': True,
                         'pivot': True, 'nonempty_frames': True}, 'used_colors': len(colors), 'artifacts': artifacts}
    (work / 'build-record.json').write_bytes(canonical(report))
    for p in tuple(work.iterdir()):
        if p.name not in artifacts and p.name != 'build-record.json': p.unlink()
    return report


def build(manifest_path: Path, output: Path | None = None, **options) -> dict:
    """Validate entirely before atomically creating a NEW output directory.

    Never overwrite inputs or previous builds. Select a new output to compare
    revisions. Source art, private manifest and native source stay outside it.
    """
    manifest_path = manifest_path.resolve()
    if output is None:
        with tempfile.TemporaryDirectory(prefix='foundation-art-') as name:
            return prepare(manifest_path, Path(name), **options)
    output = output.absolute()
    require(not output.exists() and not output.is_symlink(), 'output already exists; use a new directory to preserve prior builds')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.art-stage-', dir=output.parent) as name:
        stage = Path(name) / 'bundle'
        stage.mkdir()
        report = prepare(manifest_path, stage, **options)
        require(not output.exists(), 'output appeared during build; refusing overwrite')
        stage.rename(output)
    return report
