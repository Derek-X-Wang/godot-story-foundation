"""Neutral fixtures only. Receipt/xattrs below simulate a storage adapter, not a real upload."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

MODULE = Path(__file__).resolve().parents[2] / 'tools/checkpoints/checkpoint.py'
spec = importlib.util.spec_from_file_location('checkpoint_tool', MODULE)
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)


class Checkpoints(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / 'repo'; self.root.mkdir()
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Synthetic Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        (self.root / 'source.txt').write_text('version one\n')
        self.git('add', 'source.txt'); self.git('commit', '-qm', 'fixture base')
        c.POLICY_OVERRIDE = None

    def tearDown(self):
        c.POLICY_OVERRIDE = None
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.PIPE)

    def packed(self, name='recovery.zip'):
        path = self.base / name
        c.pack(self.root, path)
        return path

    def receipt(self, path):
        # Simulated successful application receipt for offline gate tests only.
        receipt = {'operation': 'create_library_file', 'status': 'succeeded',
                   'library_file_id': 'libfile_synthetic', 'file_id': 'file_synthetic',
                   'current_version_number': 0}
        out = self.base / 'receipt.json'; out.write_text(json.dumps(receipt))
        os.setxattr(path, 'user.library-file-id', b'libfile_synthetic')
        os.setxattr(path, 'user.library-file-version', b'0')
        return out

    def sealed(self):
        pack = self.packed()
        downloaded = self.base / 'materialized.zip'; shutil.copyfile(pack, downloaded)
        c.seal(self.root, downloaded, self.receipt(downloaded), self.base / 'restored')
        return downloaded

    def test_source_recovery_includes_untracked_authored_and_executable(self):
        (self.root / 'new.wav').write_bytes(b'new authored sound')
        (self.root / 'run.sh').write_text('#!/bin/sh\ntrue\n'); (self.root / 'run.sh').chmod(0o755)
        result = c.restore(self.packed(), self.base / 'fresh')
        self.assertEqual(result['files_restored'], 3)
        self.assertEqual((self.base / 'fresh/new.wav').read_bytes(), b'new authored sound')
        self.assertTrue((self.base / 'fresh/run.sh').stat().st_mode & 0o111)

    def test_pack_never_claims_durability(self):
        self.packed()
        self.assertEqual(c.get_state(self.root)['pending']['status'], 'pending')
        with self.assertRaisesRegex(ValueError, 'no verified'): c.guard(self.root)

    def test_guard_requires_separate_materialization_receipt_restore(self):
        pack = self.packed(); receipt = self.receipt(pack)
        with self.assertRaisesRegex(ValueError, 'separately'): c.seal(self.root, pack, receipt, self.base / 'restore')
        fresh = self.base / 'materialized.zip'; shutil.copyfile(pack, fresh)
        with self.assertRaisesRegex(ValueError, 'lack Library'): c.seal(self.root, fresh, receipt, self.base / 'restore')
        self.receipt(fresh); os.setxattr(fresh, 'user.library-file-version', b'1')
        with self.assertRaisesRegex(ValueError, 'differs'): c.seal(self.root, fresh, receipt, self.base / 'restore')

    def test_success_then_change_invalidates_boundary_and_new_pack_blocks(self):
        self.sealed(); self.assertEqual(c.guard(self.root)['status'], 'verified')
        c.begin(self.root)
        (self.root / 'source.txt').write_text('new work')
        self.assertEqual(c.guard(self.root, 'continue')['status'], 'bounded-work')
        for boundary in ['phase', 'approval-wait', 'handoff', 'release']:
            with self.assertRaisesRegex(ValueError, 'changed'): c.guard(self.root, boundary)
        self.git('add', 'source.txt'); self.git('commit', '-qm', 'work')
        self.packed('next.zip')
        with self.assertRaisesRegex(ValueError, 'pending'): c.guard(self.root, 'continue')

    def test_budget_and_session_cannot_be_reset(self):
        self.sealed(); c.begin(self.root)
        with self.assertRaisesRegex(ValueError, 'already active'): c.begin(self.root)
        state = c.get_state(self.root); state['session']['started_unix'] -= 31 * 60
        c.atomic_json(c.state_path(self.root), state)
        with self.assertRaisesRegex(ValueError, 'budget'): c.guard(self.root, 'continue')

    def test_file_budget(self):
        self.sealed(); c.begin(self.root)
        for i in range(20): (self.root / f'new{i}.txt').write_text('work')
        with self.assertRaisesRegex(ValueError, 'budget'): c.guard(self.root, 'continue')

    def test_lost_local_state_fails_closed(self):
        self.sealed(); c.state_path(self.root).unlink()
        with self.assertRaisesRegex(ValueError, 'no verified'): c.guard(self.root)

    def test_dirty_requires_emergency_flag(self):
        (self.root / 'source.txt').write_text('emergency unfinished work')
        with self.assertRaisesRegex(ValueError, 'Commit'): self.packed()
        c.pack(self.root, self.base / 'emergency.zip', allow_dirty=True)

    def test_pack_does_not_overwrite(self):
        self.packed()
        with self.assertRaisesRegex(ValueError, 'Never overwrite'): self.packed()

    def test_ignored_authored_inputs_need_explicit_policy(self):
        (self.root / '.gitignore').write_text('authored/\n')
        (self.root / 'authored').mkdir(); (self.root / 'authored/source.aseprite').write_bytes(b'authored')
        external = self.base / 'policy.json'; external.write_text(json.dumps({'include_ignored': ['authored']}))
        c.POLICY_OVERRIDE = external
        self.assertIn('authored/source.aseprite', c.snapshot(self.root)['files'])
        self.assertFalse((self.root / '.checkpoint-policy.json').exists())

    def test_secret_and_symlink_fail(self):
        (self.root / '.env').write_text('PRIVATE_TOKEN=synthetic')
        with self.assertRaisesRegex(ValueError, 'secret'): c.snapshot(self.root)
        (self.root / '.env').unlink(); (self.root / 'linked').symlink_to(self.root / 'source.txt')
        with self.assertRaisesRegex(ValueError, 'Symlink'): c.snapshot(self.root)

    def test_tamper_missing_member_traversal_and_restore_overwrite_fail(self):
        pack = self.packed(); dst = self.base / 'fresh'
        c.restore(pack, dst)
        with self.assertRaisesRegex(ValueError, 'fresh'): c.restore(pack, dst)
        with self.assertRaisesRegex(ValueError, 'checksum'): c.restore(pack, self.base / 'new', '0' * 64)
        for mutation in ['tamper', 'missing', 'traversal']:
            bad = self.base / (mutation + '.zip')
            with zipfile.ZipFile(pack) as src, zipfile.ZipFile(bad, 'w') as dest:
                for name in src.namelist():
                    if mutation == 'missing' and name == 'source/source.txt': continue
                    data = src.read(name)
                    if mutation == 'tamper' and name == 'source/source.txt': data += b'bad'
                    dest.writestr(name, data)
                if mutation == 'traversal': dest.writestr('source/../../escape', b'bad')
            with self.assertRaises(ValueError): c.restore(bad, self.base / ('new-' + mutation))
        self.assertFalse((self.base / 'escape').exists())

    def test_source_mutation_during_pack_fails(self):
        original = c.snapshot; calls = []
        def racing(root):
            calls.append(1)
            if len(calls) == 2: (root / 'source.txt').write_text('raced')
            return original(root)
        with patch.object(c, 'snapshot', side_effect=racing):
            with self.assertRaisesRegex(ValueError, 'changed'): self.packed()
        self.assertFalse((self.base / 'recovery.zip').exists())

    def test_policy_changes_and_invalid_values_fail_closed(self):
        self.sealed()
        policy = self.base / 'policy.json'; c.POLICY_OVERRIDE = policy
        with self.assertRaisesRegex(ValueError, 'missing'): c.guard(self.root)
        policy.write_text(json.dumps({'max_minutes': 100}))
        with self.assertRaisesRegex(ValueError, 'policy changed'): c.guard(self.root)
        for value in [0, -1, True, float('nan'), float('inf')]:
            policy.write_text(json.dumps({'max_minutes': value}))
            with self.assertRaisesRegex(ValueError, 'positive finite'): c.config(self.root)

    def test_large_file_budget(self):
        self.sealed(); c.begin(self.root)
        (self.root / 'large.bin').write_bytes(b'x' * (5 * 1024 * 1024))
        with self.assertRaisesRegex(ValueError, 'budget'): c.guard(self.root, 'continue')

    def test_symlinked_parent_rejected(self):
        directory = self.root / 'assets'; directory.mkdir()
        (directory / 'asset.txt').write_text('source')
        self.git('add', 'assets'); self.git('commit', '-qm', 'asset')
        target = self.base / 'outside'; directory.rename(target); directory.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Symlink'): c.snapshot(self.root)

    def test_failed_pack_blocks_previously_open_work_session(self):
        self.sealed(); c.begin(self.root)
        (self.root / 'source.txt').write_text('valuable new work')
        with patch.object(zipfile, 'ZipFile', side_effect=OSError('synthetic archive I/O failure')):
            with self.assertRaisesRegex(OSError, 'archive I/O'):
                c.pack(self.root, self.base / 'failed-pack.zip', allow_dirty=True)
        self.assertEqual(c.get_state(self.root)['pending']['status'], 'in-progress')
        with self.assertRaisesRegex(ValueError, 'pending or failed'): c.guard(self.root, 'continue')

    def test_failed_storage_receipt_never_seals(self):
        pack = self.packed(); downloaded = self.base / 'materialized.zip'; shutil.copyfile(pack, downloaded)
        receipt = self.receipt(downloaded); record = json.loads(receipt.read_text()); record['status'] = 'failed'; receipt.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'successful Library'): c.seal(self.root, downloaded, receipt, self.base / 'restore')
        self.assertEqual(c.get_state(self.root)['pending']['status'], 'pending')

    def test_bundle_requires_real_fresh_clone_and_checkout(self):
        full = self.base / 'full.bundle'; self.git('bundle', 'create', str(full), '--all')
        self.assertTrue(c.verify_bundle(full, 'main')['bundle_restorable'])
        (self.root / 'source.txt').write_text('second commit'); self.git('commit', '-qam', 'second')
        shallow = self.base / 'shallow'
        subprocess.run(['git', 'clone', '-q', '--depth=1', self.root.as_uri(), str(shallow)], check=True)
        incomplete = self.base / 'incomplete.bundle'
        subprocess.run(['git', '-C', str(shallow), 'bundle', 'create', str(incomplete), '--all'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # Reproduces the prior backup's missing-parent problem: header inspection passes.
        subprocess.run(['git', 'bundle', 'list-heads', str(incomplete)], check=True, stdout=subprocess.PIPE)
        with self.assertRaisesRegex(ValueError, 'recovery drill failed'): c.verify_bundle(incomplete, 'main')


if __name__ == '__main__': unittest.main()
