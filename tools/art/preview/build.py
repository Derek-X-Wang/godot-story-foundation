"""Build a NEW static review directory from selected PNGs / existing atlas bundles."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from .. import png
from ..manifest import canonical, digest, integer, keys, read_json, require, safe_name, source_path, text


def prepare(index: Path, stage: Path) -> dict:
    spec = read_json(index)
    keys(spec, {'title', 'assets'}, set(), 'preview index')
    text(spec['title'], 'title')
    require(isinstance(spec['assets'], list) and 0 < len(spec['assets']) <= 200, 'assets: 1..200 entries')
    entries, identities = [], set()
    for entry in spec['assets']:
        keys(entry, {'asset_id', 'label', 'kind', 'image'}, {'atlas'}, 'asset')
        safe_name(entry['asset_id'], 'asset_id')
        text(entry['label'], 'label')
        require(entry['kind'] in ('character', 'scene', 'animation'), 'kind: character, scene or animation')
        keys(entry['image'], {'path', 'sha256'}, set(), 'image')
        image = source_path(index, entry['image'])
        raw = image.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == entry['image']['sha256'], 'image changed during read')
        width, height, _ = png.decode(raw)
        atlas = None
        if 'atlas' in entry:
            keys(entry['atlas'], {'path', 'sha256'}, set(), 'atlas')
            path = source_path(index, entry['atlas'])
            atlas = read_json(path)
            require(digest(path) == entry['atlas']['sha256'], 'atlas changed during read')
            require(atlas.get('schema_version') == 1 and atlas.get('kind') == 'character_sprite', 'existing character atlas v1 required')
            require(atlas.get('asset_id') == entry['asset_id'], 'atlas asset_id mismatch')
            frames, tags = atlas.get('frames'), atlas.get('tags')
            require(isinstance(frames, list) and 0 < len(frames) <= 4096, 'atlas frames required')
            require(isinstance(tags, list) and bool(tags), 'atlas tags required')
            for frame in frames:
                rect = frame.get('rect')
                require(isinstance(rect, list) and len(rect) == 4, 'frame rect required')
                for v in rect: integer(v, 0, 4194304, 'rect')
                x, y, w, h = rect
                require(w > 0 and h > 0 and x+w <= width and y+h <= height, 'frame outside PNG')
                integer(frame.get('duration_ms'), 1, 65535, 'duration_ms')
            seen, names = [], set()
            for tag in tags:
                text(tag.get('name'), 'tag name')
                require(tag['name'] not in names, 'duplicate tag')
                names.add(tag['name'])
                integer(tag.get('start'), 0, len(frames)-1, 'tag start')
                integer(tag.get('count'), 1, len(frames), 'tag count')
                require(type(tag.get('loop')) is bool, 'tag loop required')
                indexes = list(range(tag['start'], tag['start']+tag['count']))
                require(indexes[-1] < len(frames), 'tag exceeds frames')
                require(tag.get('durations_ms') == [frames[i]['duration_ms'] for i in indexes], 'tag timing drift')
                seen.extend(indexes)
            require(seen == list(range(len(frames))), 'tags must partition ordered frames')
            # Only playback data crosses the publication boundary, not provenance notes.
            atlas = {'frames': [{k: f[k] for k in ('rect', 'duration_ms')} for f in frames],
                     'tags': [{k: t[k] for k in ('name', 'start', 'count', 'durations_ms', 'loop')} for t in tags]}
        require((entry['kind'] == 'animation') == (atlas is not None), 'animation requires atlas; still image must omit atlas')
        version = hashlib.sha256(canonical({'image': entry['image']['sha256'], 'atlas': atlas})).hexdigest()
        identity = (entry['asset_id'], version)
        require(identity not in identities, 'duplicate asset/version')
        identities.add(identity)
        name = entry['asset_id'] + '-' + version + '.png'
        (stage / name).write_bytes(raw)
        entries.append({k: entry[k] for k in ('asset_id', 'label', 'kind')} | {'version': version, 'image': name, 'width': width, 'height': height, 'atlas': atlas})
    data = {'title': spec['title'], 'assets': entries}
    # External JS assignment permits file:// review without fetch/CORS or a server.
    (stage / 'catalog.js').write_text('window.PREVIEW = ' + json.dumps(data, ensure_ascii=True) + ';\n')
    for name in ('index.html', 'viewer.js'):
        shutil.copyfile(Path(__file__).with_name(name), stage / name)
    report = {'adapter': 'static-preview-v1', 'assets': [{'asset_id': e['asset_id'], 'version': e['version']} for e in entries], 'files': {p.name: digest(p) for p in sorted(stage.iterdir())}}
    (stage / 'preview-build.json').write_bytes(canonical(report))
    return report


def build(index: Path, output: Path) -> dict:
    output = output.absolute()
    require(not output.exists() and not output.is_symlink(), 'output exists; preserve old versions')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='.preview-') as tmp:
        stage = Path(tmp) / 'site'; stage.mkdir()
        result = prepare(index.resolve(), stage)
        require(not output.exists(), 'output appeared during build')
        stage.rename(output)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('index', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.index, args.output), indent=2))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f'Preview failed: {error}\n')


if __name__ == '__main__': main()
