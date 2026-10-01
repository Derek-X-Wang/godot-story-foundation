# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
"""Optional, dependency-free Godot 4 consumer for a validated character atlas.

The atlas and its PNG are the portable contract. This adapter writes only a
SpriteFrames resource and an AnimatedSprite2D scene beside them. Copy the whole
output directory into any Godot project; its local relative references do not
assume a project root, installed addon, singleton, or runtime script.
"""
from __future__ import annotations

import json
import math
from pathlib import Path


def _string(value: str) -> str:
    """Quote resource text instead of interpolating user-controlled strings."""
    if not isinstance(value, str):
        raise ValueError('Godot resource strings must be strings')
    return json.dumps(value, ensure_ascii=False)


def _number(value: int | float) -> str:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Godot coordinates must be finite numbers')
    return str(value)


def write_godot(output_dir: Path, manifest: dict, atlas: dict) -> None:
    """Write deterministic ``sprite_frames.tres`` and ``preview.tscn``.

    Inputs are the already validated manifest and schema-1 character atlas;
    ``output_dir`` must already contain ``atlas.png`` and ``atlas.json``.
    Tags preserve order, frame ranges, loop settings, and integer millisecond
    timing. Godot's relative frame duration divided by FPS gives seconds, so
    1000 FPS with duration=milliseconds preserves unequal frame durations.

    The scene's origin is the manifest's pixel pivot, measured from the cell's
    top-left. It autoplays the first tag at unit scale. Position or scale this
    node in the consuming game's scene as needed; it owns no gameplay state.
    """
    frames = atlas['frames']
    tags = atlas['tags']
    if not frames or not tags:
        raise ValueError('Godot character output needs frames and animation tags')

    lines = [
        f'[gd_resource type="SpriteFrames" load_steps={len(frames) + 2} format=3]',
        '',
        '[ext_resource type="Texture2D" path="atlas.png" id="1_atlas"]',
    ]
    for index, frame in enumerate(frames):
        rect = frame['rect']
        if len(rect) != 4:
            raise ValueError('Godot atlas frame rect needs four coordinates')
        lines += [
            '',
            f'[sub_resource type="AtlasTexture" id="AtlasTexture_{index}"]',
            'atlas = ExtResource("1_atlas")',
            f'region = Rect2({", ".join(_number(value) for value in rect)})',
            'filter_clip = true',
        ]

    animations = []
    for tag in tags:
        start, count = tag['start'], tag['count']
        durations = tag['durations_ms']
        if (type(start) is not int or type(count) is not int
                or start < 0 or count < 1 or start + count > len(frames)
                or len(durations) != count):
            raise ValueError('Godot animation range/durations do not match the atlas')
        if type(tag['loop']) is not bool:
            raise ValueError('Godot animation loop must be a boolean')
        entries = []
        for offset, duration in enumerate(durations):
            if type(duration) is not int or duration < 1:
                raise ValueError('Godot frame duration must be positive integer milliseconds')
            entries.append('{\n"duration": %s,\n"texture": SubResource("AtlasTexture_%s")\n}'
                           % (duration, start + offset))
        animations.append('{\n"frames": [%s],\n"loop": %s,\n"name": &%s,\n"speed": 1000.0\n}'
                          % (', '.join(entries), str(tag['loop']).lower(), _string(tag['name'])))

    lines += ['', '[resource]', f'resource_name = {_string(manifest["asset_id"])}',
              'animations = [%s]' % ', '.join(animations), '']
    # A centered cell's upper-left is -cell/2. Adding cell/2-pivot places
    # the declared pivot at the node origin, including odd-sized cells.
    width, height = atlas['cell']
    pivot_x, pivot_y = atlas['pivot']
    # Validate before arithmetic so strings cannot enter the resource syntax.
    for value in (width, height, pivot_x, pivot_y):
        _number(value)
    offset_x = _number(width / 2 - pivot_x)
    offset_y = _number(height / 2 - pivot_y)
    first = _string(tags[0]['name'])
    scene = '\n'.join([
        '[gd_scene load_steps=2 format=3]',
        '',
        '[ext_resource type="SpriteFrames" path="sprite_frames.tres" id="1_frames"]',
        '',
        '[node name="CharacterPreview" type="AnimatedSprite2D"]',
        'texture_filter = 1',  # CanvasItem.TEXTURE_FILTER_NEAREST.
        'sprite_frames = ExtResource("1_frames")',
        f'animation = &{first}',
        f'autoplay = {first}',
        'centered = true',
        f'offset = Vector2({offset_x}, {offset_y})',
        '',
    ])
    (output_dir / 'sprite_frames.tres').write_text('\n'.join(lines), encoding='utf-8')
    (output_dir / 'preview.tscn').write_text(scene, encoding='utf-8')
