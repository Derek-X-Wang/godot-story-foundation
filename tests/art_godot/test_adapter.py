# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
"""Fast resource-serialization checks, independent of a Godot installation."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('art_godot_adapter', ROOT / 'tools/art/adapters/godot.py')
assert SPEC is not None and SPEC.loader is not None
ADAPTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ADAPTER)


class GodotAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.atlas = {
            'schema_version': 1, 'kind': 'character_sprite', 'asset_id': 'unit_fixture',
            'cell': [3, 5], 'pivot': [1, 4], 'columns': 2,
            'frames': [
                {'rect': [0, 0, 3, 5], 'duration_ms': 45},
                {'rect': [3, 0, 3, 5], 'duration_ms': 155},
            ],
            'tags': [
                {'name': 'idle', 'start': 0, 'count': 2, 'durations_ms': [45, 155], 'loop': True},
                {'name': 'stop', 'start': 1, 'count': 1, 'durations_ms': [155], 'loop': False},
            ],
        }
        self.manifest = {key: self.atlas[key] for key in ('asset_id', 'cell', 'pivot', 'tags')}

    def read_outputs(self) -> dict[str, str]:
        return {name: (self.output / name).read_text(encoding='utf-8')
                for name in ('sprite_frames.tres', 'preview.tscn')}

    def test_deterministic_and_no_input_mutation(self) -> None:
        before = deepcopy((self.manifest, self.atlas))
        ADAPTER.write_godot(self.output, self.manifest, self.atlas)
        first = self.read_outputs()
        ADAPTER.write_godot(self.output, self.manifest, self.atlas)
        self.assertEqual(first, self.read_outputs())
        self.assertEqual(before, (self.manifest, self.atlas))

    def test_relative_native_resources_and_nonuniform_durations(self) -> None:
        ADAPTER.write_godot(self.output, self.manifest, self.atlas)
        outputs = self.read_outputs()
        resource = outputs['sprite_frames.tres']
        self.assertIn('path="atlas.png"', resource)
        self.assertIn('region = Rect2(3, 0, 3, 5)', resource)
        self.assertIn('"duration": 45', resource)
        self.assertIn('"duration": 155', resource)
        self.assertEqual(2, resource.count('"speed": 1000.0'))
        self.assertIn('"loop": true', resource)
        self.assertIn('"loop": false', resource)
        for value in outputs.values():
            self.assertNotIn('res://', value)
            self.assertNotIn(str(self.output), value)
            self.assertNotIn('Script', value)
            self.assertNotIn('story_foundation', value)
            self.assertNotIn('dialogue_manager', value)

    def test_odd_cell_pixel_pivot_and_nearest_preview(self) -> None:
        ADAPTER.write_godot(self.output, self.manifest, self.atlas)
        scene = self.read_outputs()['preview.tscn']
        self.assertIn('type="AnimatedSprite2D"', scene)
        self.assertIn('path="sprite_frames.tres"', scene)
        self.assertIn('centered = true', scene)
        self.assertIn('offset = Vector2(0.5, -1.5)', scene)
        self.assertIn('texture_filter = 1', scene)
        self.assertIn('animation = &"idle"', scene)
        self.assertIn('autoplay = "idle"', scene)

    def test_resource_strings_are_escaped(self) -> None:
        value = 'name "quoted" \\ path\nnot_a_property = "value"'
        self.manifest['asset_id'] = value
        self.atlas['tags'][0]['name'] = value
        ADAPTER.write_godot(self.output, self.manifest, self.atlas)
        resource = self.read_outputs()['sprite_frames.tres']
        scene = self.read_outputs()['preview.tscn']
        quoted = json.dumps(value, ensure_ascii=False)
        self.assertIn('resource_name = ' + quoted, resource)
        self.assertIn('"name": &' + quoted, resource)
        self.assertIn('animation = &' + quoted, scene)
        self.assertIn('autoplay = ' + quoted, scene)
        self.assertNotIn('\nnot_a_property', resource + scene)

    def test_invalid_duration_and_ranges_reject_before_writing(self) -> None:
        cases = [
            {'start': -1}, {'start': 1}, {'start': True}, {'count': 0},
            {'count': 3}, {'count': True}, {'durations_ms': [45]},
            {'durations_ms': [45, 0]}, {'durations_ms': [45, -1]},
            {'durations_ms': [45, 1.5]}, {'durations_ms': [45, True]},
            {'loop': 'true'},
        ]
        for updates in cases:
            with self.subTest(updates=updates):
                atlas = deepcopy(self.atlas)
                atlas['tags'][0].update(updates)
                with self.assertRaises(ValueError):
                    ADAPTER.write_godot(self.output, self.manifest, atlas)
                self.assertEqual([], list(self.output.iterdir()))

    def test_invalid_coordinates_cannot_enter_resource_syntax(self) -> None:
        for value in ('0)\ninjected = true', float('nan'), float('inf'), True):
            with self.subTest(value=value):
                atlas = deepcopy(self.atlas)
                atlas['frames'][0]['rect'][0] = value
                with self.assertRaises(ValueError):
                    ADAPTER.write_godot(self.output, self.manifest, atlas)
                self.assertEqual([], list(self.output.iterdir()))
        atlas = deepcopy(self.atlas)
        atlas['pivot'][0] = 'malformed'
        with self.assertRaises(ValueError):
            ADAPTER.write_godot(self.output, self.manifest, atlas)
        self.assertEqual([], list(self.output.iterdir()))

    def test_empty_inputs_reject_before_writing(self) -> None:
        for key in ('frames', 'tags'):
            with self.subTest(key=key):
                atlas = deepcopy(self.atlas)
                atlas[key] = []
                with self.assertRaises(ValueError):
                    ADAPTER.write_godot(self.output, self.manifest, atlas)
                self.assertEqual([], list(self.output.iterdir()))


if __name__ == '__main__':
    unittest.main()
