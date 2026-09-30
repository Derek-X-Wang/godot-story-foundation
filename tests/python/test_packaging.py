"""No-network checks for deterministic packaging and project boundaries."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('package_release', ROOT / 'scripts/package_release.py')
packaging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packaging)


class PackagingTests(unittest.TestCase):
    def test_zip_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            first, second = Path(temp) / 'one.zip', Path(temp) / 'two.zip'
            packaging.deterministic_zip({'b.txt': b'b', 'a.txt': b'a'}, first)
            packaging.deterministic_zip({'a.txt': b'a', 'b.txt': b'b'}, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.namelist(), ['a.txt', 'b.txt'])

    def test_unsafe_member_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            for name in ('../secret', '/absolute', 'a/../../secret', 'a\\b'):
                with self.assertRaises(ValueError):
                    packaging.deterministic_zip({name: b'x'}, Path(temp) / 'out.zip')

    def test_collect_excludes_caches_and_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)
            (source / 'code.gd').write_text('extends RefCounted\n')
            (source / '.godot').mkdir()
            (source / '.godot/secret').write_text('cache')
            (source / 'debug.log').write_text('log')
            (source / 'icon.svg.import').write_text('upstream UID/import metadata')
            self.assertEqual(set(packaging.collect_tree(source, 'addons/example')),
                             {'addons/example/code.gd', 'addons/example/icon.svg.import'})
            (source / 'alias').symlink_to(source / 'code.gd')
            with self.assertRaises(ValueError):
                packaging.collect_tree(source, 'addons/example')

    def test_source_root_and_ancestor_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'outside').mkdir()
            (root / 'outside/child').mkdir()
            (root / 'outside/child/private.txt').write_text('private')
            (root / 'alias').symlink_to(root / 'outside', target_is_directory=True)
            for source in (root / 'alias', root / 'alias/child'):
                with self.assertRaises(ValueError):
                    packaging.collect_tree(source, 'addons/example')

    def test_authoring_is_outside_godot_project(self):
        game = ROOT / 'examples/village/game'
        self.assertTrue((game / 'project.godot').is_file())
        self.assertTrue((game.parent / 'authoring').is_dir())
        self.assertFalse((ROOT / 'project.godot').exists())
        self.assertFalse(any(p.name in {'packet.json', 'response.json', 'review.json', 'approval.fixture.json'} for p in game.rglob('*')))


if __name__ == '__main__':
    unittest.main()
