"""Scene-only package allowlist, provenance and isolation regression tests."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import package_scene
sys.path.pop(0)


class ScenePackagingTests(unittest.TestCase):
    def test_scene_only_deterministic_package_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            first = package_scene.package(root / 'first')
            second = package_scene.package(root / 'second')
            self.assertEqual(first.read_bytes(), second.read_bytes())
            digest, filename = first.with_suffix('.zip.sha256').read_text().split()
            self.assertEqual(filename, first.name)
            self.assertEqual(digest, hashlib.sha256(first.read_bytes()).hexdigest())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(set(archive.namelist()), set(package_scene.MEMBERS) | {'SCENE-MANIFEST.json'})
                self.assertEqual(len(archive.namelist()), 6)
                manifest = json.loads(archive.read('SCENE-MANIFEST.json'))
                self.assertEqual(manifest['scene_api_version'], 1)
                self.assertEqual(manifest['package_kind'], 'optional-scene-primitives')
                self.assertEqual(set(manifest['files']), set(package_scene.MEMBERS))
                for name, expected in manifest['files'].items():
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), expected)
                    self.assertEqual(archive.read(name), (ROOT / name).read_bytes())

    def test_missing_or_symlinked_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(package_scene, 'ROOT', root):
                with self.assertRaises(ValueError):
                    package_scene.package(root / 'output')
                (root / 'license.txt').write_text('fixture')
                (root / 'LICENSE').symlink_to(root / 'license.txt')
                with self.assertRaises(ValueError):
                    package_scene.package(root / 'output')

    def test_scene_source_has_no_resource_or_autoload_dependencies(self):
        for name in ('rect_navigation', 'depth_order'):
            source = (ROOT / f'addons/story_foundation/scene/{name}.gd').read_text()
            for token in ('preload(', 'load(', 'get_node(', 'class_name ', 'res://', 'user://'):
                self.assertNotIn(token, source)
            uid = (ROOT / f'addons/story_foundation/scene/{name}.gd.uid').read_text()
            self.assertRegex(uid, r'^uid://[a-z0-9]+\n$')


if __name__ == '__main__':
    unittest.main()
