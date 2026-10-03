"""Audio-only package allowlist, provenance and isolation regression tests."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import package_audio
import test_audio
sys.path.pop(0)

EXPECTED_MEMBERS = {
    'LICENSE',
    'addons/story_foundation/audio/audio_bus_settings.gd',
    'addons/story_foundation/audio/gain_envelope.gd',
    'addons/story_foundation/audio/web_safe_audio_buses.gd',
}


class AudioPackagingTests(unittest.TestCase):
    def make_sources(self, root):
        for name in EXPECTED_MEMBERS:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f'Synthetic package fixture: {name}\n', encoding='utf-8')

    def test_audio_only_deterministic_package_and_hashes(self):
        self.assertEqual(set(package_audio.MEMBERS), EXPECTED_MEMBERS)
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            first = package_audio.package(root / 'first')
            second = package_audio.package(root / 'second')
            self.assertEqual(first.name, 'godot-story-foundation-audio-api1.zip')
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(first.with_suffix('.zip.sha256').read_bytes(),
                             second.with_suffix('.zip.sha256').read_bytes())
            digest, filename = first.with_suffix('.zip.sha256').read_text().split()
            self.assertEqual(filename, first.name)
            self.assertEqual(digest, hashlib.sha256(first.read_bytes()).hexdigest())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(set(archive.namelist()), EXPECTED_MEMBERS | {'AUDIO-MANIFEST.json'})
                self.assertEqual(len(archive.namelist()), 5)
                manifest = json.loads(archive.read('AUDIO-MANIFEST.json'))
                self.assertEqual(manifest['audio_api_version'], 1)
                self.assertEqual(manifest['package_kind'], 'optional-audio-primitives')
                self.assertEqual(set(manifest['files']), EXPECTED_MEMBERS)
                for name, expected in manifest['files'].items():
                    self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), expected)
                    self.assertEqual(archive.read(name), (ROOT / name).read_bytes())

    def test_unlisted_files_and_generated_uids_are_excluded(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            self.make_sources(root)
            for name in ('addons/story_foundation/audio/unrelated.gd',
                         'addons/story_foundation/audio/audio_bus_settings.gd.uid',
                         'addons/story_foundation/audio/music.wav',
                         'addons/story_foundation/runtime/private.gd', '.godot/imported/cache'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('Excluded synthetic fixture\n', encoding='utf-8')
            with patch.object(package_audio, 'ROOT', root):
                package = package_audio.package(root / 'output')
            with zipfile.ZipFile(package) as archive:
                self.assertEqual(set(archive.namelist()), EXPECTED_MEMBERS | {'AUDIO-MANIFEST.json'})

    def test_missing_or_non_file_sources_rejected(self):
        for name in sorted(EXPECTED_MEMBERS):
            for replacement in ('missing', 'directory'):
                with self.subTest(name=name, replacement=replacement), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    self.make_sources(root)
                    path = root / name
                    path.unlink()
                    if replacement == 'directory':
                        path.mkdir()
                    with patch.object(package_audio, 'ROOT', root), self.assertRaises(ValueError):
                        package_audio.package(root / 'output')
                    self.assertFalse((root / 'output').exists())

    def test_symlinked_source_rejected(self):
        for name in sorted(EXPECTED_MEMBERS):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.make_sources(root)
                path = root / name
                path.rename(root / 'target.txt')
                path.symlink_to(root / 'target.txt')
                with patch.object(package_audio, 'ROOT', root), self.assertRaises(ValueError):
                    package_audio.package(root / 'output')
                self.assertFalse((root / 'output').exists())

    def test_symlinked_source_ancestor_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_sources(root)
            source = root / 'addons/story_foundation/audio'
            source.rename(root / 'actual-audio')
            source.symlink_to(root / 'actual-audio', target_is_directory=True)
            with patch.object(package_audio, 'ROOT', root), self.assertRaises(ValueError):
                package_audio.package(root / 'output')
            self.assertFalse((root / 'output').exists())

    def test_audio_sources_have_no_resource_global_or_autoload_dependencies(self):
        for name in sorted(EXPECTED_MEMBERS - {'LICENSE'}):
            with self.subTest(name=name):
                source = (ROOT / name).read_text(encoding='utf-8')
                # Ignore explanatory comments; caller-provided ConfigFile paths and
                # the settings helper's own load() method are legitimate API.
                code = '\n'.join(line for line in source.splitlines() if not line.lstrip().startswith('#'))
                self.assertRegex(code, r'(?m)^extends RefCounted\s*$')
                for pattern in (r'\bpreload\s*\(', r'\bResourceLoader\b', r'\bclass_name\s+',
                                r'\bget_node(?:_or_null)?\s*\(', r'\bget_tree\s*\(',
                                r'\bEngine\s*\.\s*get_singleton\s*\(', r'\bres://', r'\buid://',
                                r'\bAudioStream[A-Za-z0-9_]*\b'):
                    self.assertNotRegex(code, pattern)
                # A bare global load() would introduce a resource dependency.
                # Method declarations and obj.load() (ConfigFile) are permitted.
                without_declarations = re.sub(r'\bfunc\s+load\s*\(', 'func settings_load(', code)
                self.assertNotRegex(without_declarations, r'(?<![\w.])load\s*\(')

    def test_runner_uses_isolated_projects_and_fresh_relocation(self):
        calls = []

        def fake_run(godot, project, environment, arguments):
            self.assertEqual(godot, '/fixture/godot')
            if arguments == ['--editor', '--import']:
                self.assertEqual({path.name for path in project.iterdir()},
                                 {'project.godot', 'selected.gd', 'run.gd'})
                module = project.name.removesuffix('-relocated')
                self.assertEqual((project / 'selected.gd').read_bytes(),
                                 (ROOT / f'addons/story_foundation/audio/{module}.gd').read_bytes())
                self.assertNotIn('[autoload]', (project / 'project.godot').read_text())
                if project.name.endswith('-relocated'):
                    self.assertFalse((project.parent / module).exists())
                # Simulate generated editor state: none may be copied on relocation.
                (project / '.godot').mkdir()
                (project / 'selected.gd.uid').write_text('uid://synthetic\n')
                (project / 'run.gd.uid').write_text('uid://synthetictest\n')
            calls.append((project.name, arguments))
            return 'Audio synthetic check passed\n'

        with patch.object(test_audio.shutil, 'which', return_value='/fixture/godot'), \
                patch.object(test_audio, 'run', side_effect=fake_run), \
                contextlib.redirect_stdout(io.StringIO()):
            test_audio.check()
        expected = []
        for module in ('web_safe_audio_buses', 'audio_bus_settings', 'gain_envelope'):
            for project in (module, f'{module}-relocated'):
                expected.extend([(project, ['--editor', '--import']),
                                 (project, ['--script', 'res://run.gd'])])
        self.assertEqual(calls, expected)

    def test_runner_rejects_errors_and_missing_test_result(self):
        for code, output in ((1, 'Audio failed\n'), (0, 'SCRIPT ERROR: failure\n'),
                             (0, 'ERROR: failure\n'), (0, '  ERROR: failure\n'),
                             (0, 'Godot started with no test result\n')):
            with self.subTest(code=code, output=output):
                result = subprocess.CompletedProcess([], code, stdout=output)
                with patch.object(test_audio.subprocess, 'run', return_value=result), self.assertRaises(RuntimeError):
                    test_audio.run('godot', Path('synthetic'), {}, ['--script', 'res://run.gd'])


if __name__ == '__main__':
    unittest.main()
