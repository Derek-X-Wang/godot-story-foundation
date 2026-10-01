"""Strict manifest v1 semantics, mirrored by schemas/character-sprite.schema.json."""
from __future__ import annotations
import re
from ..manifest import integer, keys, require, safe_name, text, validate_provenance


def validate_manifest(m: dict, allow_unknown: bool = False) -> list[str]:
    keys(m, {'schema_version', 'asset_id', 'kind', 'source', 'provenance', 'cell', 'pivot',
             'columns', 'palette', 'hard_alpha', 'tags'}, set(), 'manifest')
    require(type(m['schema_version']) is int and m['schema_version'] == 1, 'unsupported manifest schema_version')
    safe_name(m['asset_id'], 'asset_id')
    require(m['kind'] == 'character_sprite', 'this subpipeline accepts character_sprite only; portraits/scenes are separate outputs')
    s = m['source']
    keys(s, {'adapter', 'path', 'sha256'}, {'layers', 'pivot_slice'}, 'source')
    require(s['adapter'] in ('png', 'aseprite'), 'source.adapter must be png or aseprite')
    text(s['path'], 'source.path')
    require(isinstance(s['sha256'], str) and re.fullmatch('[a-f0-9]{64}', s['sha256']), 'source.sha256 must be a lowercase SHA-256')
    require(s['adapter'] == 'aseprite' or not ({'layers', 'pivot_slice'} & s.keys()), 'PNG source has no native layers/pivot_slice')
    if 'layers' in s:
        require(isinstance(s['layers'], list) and 1 <= len(s['layers']) <= 4096, 'source.layers must contain 1..4096 names')
        for layer in s['layers']: text(layer, 'source.layers entry')
        require(len(set(s['layers'])) == len(s['layers']), 'duplicate source.layers')
    if 'pivot_slice' in s: text(s['pivot_slice'], 'source.pivot_slice')
    for field in ('cell', 'pivot'):
        require(isinstance(m[field], list) and len(m[field]) == 2, f'{field} must have two coordinates')
    for v in m['cell']: integer(v, 1, 1024, 'cell')
    for i, v in enumerate(m['pivot']): integer(v, 0, m['cell'][i], 'pivot (pixel-edge coordinates)')
    integer(m['columns'], 1, 4096, 'columns')
    require(m['hard_alpha'] is True, 'pixel sprite v1 requires hard_alpha=true')
    require(isinstance(m['palette'], list) and 1 <= len(m['palette']) <= 256, 'palette must contain 1..256 RGBA colors')
    for color in m['palette']:
        require(isinstance(color, str) and re.fullmatch('#[a-f0-9]{8}', color), 'palette entries must be lowercase #rrggbbaa')
        require(color[-2:] in ('00', 'ff'), 'palette contains nonbinary alpha')
        require(color[-2:] != '00' or color == '#00000000', 'transparent palette color must be canonical #00000000')
    require(len(set(m['palette'])) == len(m['palette']), 'duplicate palette colors')
    require(isinstance(m['tags'], list) and 1 <= len(m['tags']) <= 256, 'tags must be a nonempty list')
    cursor, names = 0, set()
    for tag in m['tags']:
        keys(tag, {'name', 'start', 'count', 'durations_ms', 'loop'}, set(), 'tag')
        safe_name(tag['name'], 'tag.name')
        require(tag['name'] not in names, 'duplicate tag name')
        names.add(tag['name'])
        integer(tag['start'], 0, 4095, 'tag.start')
        integer(tag['count'], 1, 4096, 'tag.count')
        require(tag['start'] == cursor, 'tags must partition all frames in order, without overlaps or gaps')
        require(type(tag['loop']) is bool, 'tag.loop must be boolean')
        require(isinstance(tag['durations_ms'], list) and len(tag['durations_ms']) == tag['count'], 'tag durations_ms must match count')
        for duration in tag['durations_ms']: integer(duration, 1, 65535, 'duration_ms')
        cursor += tag['count']
    require(cursor <= 4096 and m['columns'] <= cursor, 'frame count/columns exceeds supported range')
    require(m['cell'][0] * m['columns'] * m['cell'][1] * ((cursor + m['columns'] - 1) // m['columns']) <= 4_194_304,
            'sprite sheet exceeds 4,194,304 pixels')
    return validate_provenance(m['provenance'], allow_unknown)


def frame_durations(m: dict) -> list[int]:
    return [duration for tag in m['tags'] for duration in tag['durations_ms']]
