"""Offline adversarial checks for public dependency downloads/extraction."""
import hashlib
import importlib.util
import io
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('fetch_dependencies', ROOT / 'scripts/fetch_dependencies.py')
deps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deps)


class DependencyTests(unittest.TestCase):
    def archive(self, name='safe/file', data=b'x', mode=0):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            info = zipfile.ZipInfo(name)
            info.external_attr = mode << 16
            archive.writestr(info, data)
        stream.seek(0)
        return zipfile.ZipFile(stream)

    def test_unsafe_paths(self):
        for name in ('../file', '/absolute', 'C:/file', 'a\\file', 'a//file', 'a/./file'):
            with self.subTest(name=name), self.archive(name) as archive, self.assertRaises(ValueError):
                deps.safe_zip_members(archive, 100)

    def test_symlink_and_size(self):
        with self.archive(mode=stat.S_IFLNK | 0o777) as archive, self.assertRaises(ValueError):
            deps.safe_zip_members(archive, 100)
        with self.archive(data=b'large') as archive, self.assertRaises(ValueError):
            deps.safe_zip_members(archive, 2)

    def test_hash_verification_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'archive.zip'
            path.write_bytes(b'test')
            deps.verify_archive(path, hashlib.sha256(b'test').hexdigest(), 4)
            with self.assertRaises(ValueError):
                deps.verify_archive(path, '0' * 64, 4)
            with self.assertRaises(ValueError):
                deps.verify_archive(path, hashlib.sha256(b'test').hexdigest(), 3)

    def test_non_https_refused_without_network(self):
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(ValueError):
            deps.fetch_verified('http://example.invalid/dependency', Path(temp) / 'dep.zip', '0' * 64, 5)


if __name__ == '__main__':
    unittest.main()
