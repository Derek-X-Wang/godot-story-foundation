#!/usr/bin/env python3
"""Optional, dependency-free source checkpoints. Trusts the authorized storage adapter.

A local archive is pending. Only a durable create receipt AND independently
materialized bytes AND a fresh restore drill can mark it verified. This is a
workflow guard, not a security boundary or a platform persistence guarantee.
"""
import argparse
import fnmatch
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

SCHEMA = 1
POLICY_OVERRIDE = None
BUILTIN_EXCLUDES = {'.git', '.checkpoints', '.godot', '.build', '.deps',
                    '__pycache__', 'node_modules', '.sites-runtime'}
SECRET_NAMES = {'.env', '.aws', '.ssh', 'credentials.json', 'id_rsa', 'id_ed25519'}


def fail(message):
    raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def read_json(path):
    return json.loads(Path(path).read_text())


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_bytes(encoded(value))
    temp.replace(path)


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)


def config(root):
    path = Path(POLICY_OVERRIDE) if POLICY_OVERRIDE else root / '.checkpoint-policy.json'
    if POLICY_OVERRIDE and not path.is_file():
        fail('Explicit checkpoint policy is missing')
    value = read_json(path) if path.exists() else {}
    if not isinstance(value, dict) or set(value) - {'schema', 'exclude', 'include_ignored', 'max_minutes', 'max_changed_files', 'max_changed_bytes'}:
        fail('Unknown checkpoint policy fields')
    if value.get('schema', 1) != SCHEMA:
        fail('Unsupported checkpoint policy schema')
    cfg = {'schema': SCHEMA, 'exclude': [], 'include_ignored': [],
            'max_minutes': 30, 'max_changed_files': 20,
            'max_changed_bytes': 5 * 1024 * 1024, **value}
    for key in ('max_minutes', 'max_changed_files', 'max_changed_bytes'):
        if type(cfg[key]) not in (int, float) or not math.isfinite(cfg[key]) or cfg[key] <= 0:
            fail('Checkpoint budgets must be positive finite numbers: ' + key)
    for key in ('exclude', 'include_ignored'):
        if not isinstance(cfg[key], list) or not all(isinstance(item, str) and item for item in cfg[key]):
            fail('Checkpoint path selections must be lists of strings: ' + key)
    return cfg


def safe_path(name):
    p = PurePosixPath(name)
    if not name or p.is_absolute() or '..' in p.parts or '\\' in name or str(p) != name:
        fail('Unsafe relative path: ' + name)
    return p


def snapshot(root):
    cfg = config(root)
    raw = git(root, 'ls-files', '-z', '--cached', '--others', '--exclude-standard')
    names = set(raw.decode().split('\0')) - {''}
    # Explicitly include ignored authored input directories, never caches or secrets.
    for value in cfg['include_ignored']:
        safe_path(value)
        path = root / value
        if path.is_symlink():
            fail('Symlinked authored input requires an adapter: ' + value)
        if not path.exists():
            fail('Declared authored input is missing: ' + value)
        names.update(str(p.relative_to(root)) for p in ([path] if path.is_file() else path.rglob('*')) if p.is_file() or p.is_symlink())
    files, excluded = {}, []
    for name in sorted(names):
        p = safe_path(name)
        if any(part in BUILTIN_EXCLUDES for part in p.parts) or any(fnmatch.fnmatchcase(name, pattern) for pattern in cfg['exclude']):
            excluded.append(name)
            continue
        if any(part in SECRET_NAMES or part.endswith(('.pem', '.key', '.p12')) or (part.startswith('.env.') and part != '.env.example') for part in p.parts):
            fail('Possible secret requires removal from checkpoint scope: ' + name)
        path = root / name
        if any((root / Path(*p.parts[:i])).is_symlink() for i in range(1, len(p.parts) + 1)):
            fail('Symlink requires an explicit portable source adapter: ' + name)
        if not path.exists():  # Record deletions through the absent manifest entry.
            continue
        if not path.is_file():
            fail('Non-file source (including submodules) requires an adapter: ' + name)
        data = path.read_bytes()
        files[name] = {'sha256': digest(data), 'bytes': len(data),
                       'executable': bool(path.stat().st_mode & 0o111)}
    if not files:
        fail('Empty source checkpoint')
    dirty = git(root, 'status', '--porcelain=v1', '--untracked-files=no').decode().strip()
    return {'schema': SCHEMA, 'head': git(root, 'rev-parse', 'HEAD').decode().strip(),
            'dirty_tracked': bool(dirty), 'files': files, 'excluded': excluded,
            'source_sha256': digest(encoded(files)), 'policy': cfg, 'policy_sha256': digest(encoded(cfg))}


def state_path(root):
    git_path = Path(git(root, 'rev-parse', '--git-path', 'durable-checkpoints/state.json').decode().strip())
    return git_path if git_path.is_absolute() else root / git_path


def get_state(root):
    p = state_path(root)
    return read_json(p) if p.exists() else {}


def pack(root, output, allow_dirty=False):
    output = Path(output).resolve()
    # Invalidate continuation BEFORE snapshot/archive I/O, not only on success.
    # An interrupted/failed checkpoint must never leave the old gate usable.
    state = get_state(root)
    state['pending'] = {'status': 'in-progress', 'archive': str(output), 'started_unix': time.time()}
    atomic_json(state_path(root), state)
    if output.exists():
        fail('Never overwrite a checkpoint pack; choose a new output path')
    if output.is_relative_to(root) and not output.is_relative_to(root / '.checkpoints'):
        fail('Write packs outside source root or inside .checkpoints/')
    initial = snapshot(root)
    if initial['dirty_tracked'] and not allow_dirty:
        fail('Commit reviewed tracked changes first; --allow-dirty is emergency preservation only')
    manifest = {**initial, 'created_unix': time.time(), 'format': 'source-recovery-v1',
                'scope': 'Exact source tree, not Git history, caches, dependencies or a built release'}
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + '.tmp')
    try:
        with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('manifest.json', encoded(manifest))
            for name, entry in manifest['files'].items():
                data = (root / name).read_bytes()
                if digest(data) != entry['sha256']:
                    fail('Source changed during pack: ' + name)
                archive.writestr('source/' + name, data)
        final = snapshot(root)
        if final['source_sha256'] != initial['source_sha256'] or final['head'] != initial['head'] or final['policy_sha256'] != initial['policy_sha256']:
            fail('Source changed during checkpoint; retry at a quiet boundary')
        temp.replace(output)
    finally:
        if temp.exists():
            temp.unlink()
    record = {'status': 'pending', 'archive': str(output), 'archive_sha256': digest(output.read_bytes()),
              'head': manifest['head'], 'source_sha256': manifest['source_sha256'], 'policy_sha256': manifest['policy_sha256'],
              'created_unix': manifest['created_unix']}
    atomic_json(output.with_suffix(output.suffix + '.pending.json'), record)
    state = get_state(root)
    state['pending'] = record
    atomic_json(state_path(root), state)
    return record


def restore(archive_path, destination, expected_hash=None):
    archive_path, destination = Path(archive_path), Path(destination)
    actual = digest(archive_path.read_bytes())
    if expected_hash and actual != expected_hash:
        fail('Archive checksum mismatch')
    if destination.exists():
        fail('Restore destination must be fresh and absent')
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            fail('Duplicate archive member')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('schema') != SCHEMA or manifest.get('format') != 'source-recovery-v1':
            fail('Unsupported source recovery format')
        expected = {'manifest.json'} | {'source/' + name for name in manifest['files']}
        if set(names) != expected:
            fail('Archive inventory does not match manifest')
        if digest(encoded(manifest['files'])) != manifest['source_sha256']:
            fail('Manifest source checksum mismatch')
        for name in manifest['files']:
            safe_path(name)
        # Validate every entry before writing any source; no extractall/path traversal.
        for name, entry in manifest['files'].items():
            data = archive.read('source/' + name)
            if len(data) != entry['bytes'] or digest(data) != entry['sha256']:
                fail('Source checksum mismatch: ' + name)
        destination.mkdir(parents=True)
        for name, entry in manifest['files'].items():
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read('source/' + name))
            path.chmod(0o755 if entry['executable'] else 0o644)
        for name, entry in manifest['files'].items():
            if digest((destination / name).read_bytes()) != entry['sha256']:
                fail('Restored file checksum mismatch: ' + name)
    return {'archive_sha256': actual, 'source_sha256': manifest['source_sha256'],
            'files_restored': len(manifest['files']), 'head': manifest['head'],
            'dirty_tracked': manifest['dirty_tracked'], 'files': manifest['files'], 'policy_sha256': manifest['policy_sha256']}


def seal(root, downloaded, receipt_path, restore_to):
    state = get_state(root)
    pending = state.get('pending')
    if not pending:
        fail('No pending checkpoint; pack first')
    downloaded = Path(downloaded).resolve()
    if downloaded == Path(pending['archive']).resolve() or (Path(pending['archive']).exists() and os.path.samefile(downloaded, pending['archive'])):
        fail('Verification requires separately materialized durable bytes, not the local pack')
    receipt = read_json(receipt_path)
    receipt = receipt.get('result', receipt)
    if receipt.get('status') != 'succeeded' or receipt.get('operation') not in ('create_library_file', 'replace_library_file') or not receipt.get('library_file_id') or not receipt.get('file_id') or receipt.get('current_version_number') is None:
        fail('Require the unchanged successful Library create/replace result')
    try:
        identity = os.getxattr(downloaded, 'user.library-file-id').decode()
        version = os.getxattr(downloaded, 'user.library-file-version').decode()
    except OSError:
        fail('Downloaded bytes lack Library identity; materialize through its supported adapter')
    if identity != receipt['library_file_id'] or version != str(receipt['current_version_number']):
        fail('Materialized Library identity/version differs from receipt')
    proof = restore(downloaded, restore_to, pending['archive_sha256'])
    current = snapshot(root)
    if current['source_sha256'] != proof['source_sha256'] or current['head'] != proof['head'] or current['policy_sha256'] != proof['policy_sha256']:
        fail('Durable checkpoint restored, but working source advanced; checkpoint again before crossing boundary')
    verified = {**pending, **proof, 'status': 'verified', 'verified_unix': time.time(),
                'library_file_id': identity, 'library_version': version,
                'file_id': receipt['file_id'], 'restore_path': str(Path(restore_to).resolve())}
    atomic_json(state_path(root), {'verified': verified})
    return {k: v for k, v in verified.items() if k != 'files'}


def guard(root, boundary='phase'):
    state, current, cfg = get_state(root), snapshot(root), config(root)
    verified = state.get('verified')
    if not verified or verified.get('status') != 'verified':
        fail('BLOCKED: no verified durable checkpoint; upload, materialize, restore and seal first')
    if state.get('pending'):
        fail('BLOCKED: checkpoint upload/verification is pending or failed')
    if current['policy_sha256'] != verified['policy_sha256']:
        fail('BLOCKED: checkpoint policy changed; checkpoint the reviewed policy before continuing')
    same = current['source_sha256'] == verified['source_sha256'] and current['head'] == verified['head']
    if boundary != 'continue':
        if not same:
            fail('BLOCKED: source changed since verified checkpoint; checkpoint before ' + boundary)
        if boundary == 'release' and current['dirty_tracked']:
            fail('BLOCKED: emergency dirty snapshot cannot authorize release; commit and checkpoint first')
    else:
        session = state.get('session')
        if not session:
            fail('BLOCKED: begin a bounded work session first')
        previous = verified['files']
        changed = [n for n in set(current['files']) | set(previous) if current['files'].get(n) != previous.get(n)]
        size = sum(max(current['files'].get(n, {}).get('bytes', 0), previous.get(n, {}).get('bytes', 0)) for n in changed)
        elapsed = (time.time() - session['started_unix']) / 60
        if elapsed >= cfg['max_minutes'] or len(changed) >= cfg['max_changed_files'] or size >= cfg['max_changed_bytes']:
            fail('BLOCKED: bounded work budget reached; commit and make a durable checkpoint now')
    return {'status': 'verified' if same else 'bounded-work', 'boundary': boundary,
            'library_file_id': verified['library_file_id'], 'checkpoint_head': verified['head']}


def begin(root):
    result = guard(root, 'phase')
    state = get_state(root)
    if state.get('session'):
        fail('Session already active; its time budget cannot be reset without a new durable checkpoint')
    state['session'] = {'started_unix': time.time()}
    atomic_json(state_path(root), state)
    return result


def verify_bundle(bundle, ref):
    """A bundle header/list-heads/verify alone is not an actual recovery drill."""
    with tempfile.TemporaryDirectory(prefix='checkpoint-bundle-drill-') as directory:
        target = Path(directory) / 'restored'
        try:
            subprocess.run(['git', 'clone', '--quiet', '--no-checkout', str(Path(bundle).resolve()), str(target)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(['git', '-C', str(target), 'checkout', '--quiet', ref], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            subprocess.run(['git', '-C', str(target), 'fsck', '--connectivity-only'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as error:
            fail('Bundle recovery drill failed; do not claim self-contained history: ' + error.stderr.decode().strip())
        return {'status': 'verified', 'bundle_restorable': True,
                'head': git(target, 'rev-parse', 'HEAD').decode().strip(),
                'scope': 'Only history actually present in this bundle; not a claim of all remote history'}


def main(argv=None):
    global POLICY_OVERRIDE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--policy', type=Path, help='Optional policy outside an immutable consumer tree')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('pack'); p.add_argument('--output', required=True); p.add_argument('--allow-dirty', action='store_true')
    p = sub.add_parser('restore'); p.add_argument('--archive', required=True); p.add_argument('--to', required=True); p.add_argument('--sha256')
    p = sub.add_parser('seal'); p.add_argument('--downloaded', required=True); p.add_argument('--receipt', required=True); p.add_argument('--restore-to', required=True)
    for name in ('guard', 'run'):
        p = sub.add_parser(name); p.add_argument('--boundary', choices=['continue', 'phase', 'approval-wait', 'handoff', 'release'], default='phase')
        if name == 'run': p.add_argument('argv', nargs=argparse.REMAINDER)
    sub.add_parser('begin')
    p = sub.add_parser('verify-bundle'); p.add_argument('--bundle', required=True); p.add_argument('--ref', required=True)
    a = parser.parse_args(argv); root = a.root.resolve(); POLICY_OVERRIDE = a.policy
    try:
        if a.command == 'verify-bundle': result = verify_bundle(a.bundle, a.ref)
        elif a.command == 'pack': result = pack(root, a.output, a.allow_dirty)
        elif a.command == 'restore': result = restore(a.archive, a.to, a.sha256); result.pop('files')
        elif a.command == 'seal': result = seal(root, a.downloaded, a.receipt, a.restore_to)
        elif a.command == 'begin': result = begin(root)
        else:
            result = guard(root, a.boundary)
            if a.command == 'run':
                command = a.argv[1:] if a.argv[:1] == ['--'] else a.argv
                if not command: fail('A command is required after --')
                status = subprocess.run(command, cwd=root).returncode
                if status: return status
                # Post-check detects an oversized command; cannot undo or prevent its edits.
                result = guard(root, a.boundary)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        print(json.dumps({'status': 'blocked', 'error': str(error)}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
