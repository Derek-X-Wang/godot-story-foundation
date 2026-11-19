"""Export/import an existing static portrait for private review, never for release."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import zipfile

from .. import design, png
from ..manifest import ArtError, canonical, keys, require, source_path

INTENT = 'import_existing_static_portrait'
MAX_JSON = 1_048_576
MAX_PNG = 20 * MAX_JSON


def _read(path: Path, limit: int) -> bytes:
    require(path.is_file() and path.stat().st_size <= limit, 'invalid input file type or size')
    with path.open('rb') as handle:
        raw = handle.read(limit + 1)
    require(len(raw) <= limit, 'input grew beyond size limit')
    return raw


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _private_directory(path: Path) -> Path:
    require(path.is_dir() and not path.is_symlink(), 'choose an existing private directory')
    root = path.resolve()
    require(not any((p / 'project.godot').is_file() for p in (root, *root.parents)),
            'keep pending authoring output and approval store outside Godot project roots')
    return root


def _publish(root: Path, name: str, write, revalidate=lambda: None) -> Path:
    # A single-file handoff can commit atomically without replacing an existing
    # target. The caller owns the directory and must keep its path stable.
    target = root / name
    require(not target.exists() and not target.is_symlink(), 'output already exists')
    with tempfile.TemporaryDirectory(prefix='.static-portrait-', dir=root) as tmp:
        stage = Path(tmp) / 'sealed'
        with stage.open('xb') as handle:
            os.chmod(stage, stat.S_IRUSR | stat.S_IWUSR)
            write(handle)
            handle.flush()
            os.fsync(handle.fileno())
        revalidate()
        os.link(stage, target)
    return target


def _request(concept: Path, sheet: Path, image: Path, *, character_id: str,
             concept_revision: str, design_revision: str) -> tuple[dict, bytes]:
    paths = {'concept': concept, 'design': sheet}
    records, refs = {}, {}
    for stage, revision in (('concept', concept_revision), ('design', design_revision)):
        path = paths[stage]
        # This first digest is an in-run consistency check, not an authority.
        # Approval requires the separately controlled receipt on import.
        record_sha = _sha(_read(path, MAX_JSON))
        checked = design.check(path, character_id=character_id, revision=revision,
                               expected_record_sha256=record_sha)
        require(checked['stage'] == stage, f'expected {stage} record')
        record = design.read_json(path)
        require(_sha(_read(path, MAX_JSON)) == record_sha, f'{stage} record changed during read')
        records[stage] = record
        refs[stage] = {
            'revision': revision,
            'record_sha256': record_sha,
            'review_basis_sha256': checked['review_basis_sha256'],
            'artifact_sha256': record['output']['sha256'],
        }
    expectations = {
        'upstream_record': (concept, refs['concept']['record_sha256']),
        'concept_image': (source_path(concept, records['concept']['output']),
                          refs['concept']['artifact_sha256']),
    }
    for role, (path, sha) in expectations.items():
        matches = [r for r in records['design']['references'] if r['role'] == role]
        require(len(matches) == 1 and matches[0]['sha256'] == sha
                and source_path(sheet, matches[0]).resolve() == path.resolve(),
                f'design does not reference the exact selected concept via {role}')
    raw = _read(image, MAX_PNG)
    return {'schema_version': 1, 'kind': 'static_portrait_import_request',
            'intent': INTENT, 'character_id': character_id, 'lineage': refs,
            'source_png_sha256': _sha(raw)}, raw


def export_request(concept: Path, sheet: Path, image: Path, output: Path, **identity) -> dict:
    request, _ = _request(concept, sheet, image, **identity)
    _publish(_private_directory(output.parent), output.name,
             lambda handle: handle.write(canonical(request)))
    return request


def _approval(directory: Path, request: dict, concept: Path, sheet: Path,
              image: Path, packet: Path) -> str:
    gate = request['lineage']['design']
    current = design.check(sheet, character_id=request['character_id'],
                           revision=gate['revision'], expected_record_sha256=gate['record_sha256'])
    require(current['declared_human_review_status'] == 'accepted',
            'design is not accepted; pending/rejected designs cannot be imported')
    # The reviewer name stays local and must match the accepted record. It is
    # not authentication: only the configured caller-controlled store carries
    # authority, and its origin/access policy belongs to the caller.
    reviewer = design.read_json(sheet)['review']['reviewer']
    root = _private_directory(directory)
    for location in (concept, sheet, image, packet):
        parent = location.resolve().parent
        require(not root.is_relative_to(parent) and not parent.is_relative_to(root),
                'approval store must be separate from all input directories')
    receipt = root / (gate['record_sha256'] + '.json')
    require(receipt.is_file() and not receipt.is_symlink(), 'trusted approval receipt missing')
    raw = _read(receipt, MAX_JSON)
    value = design.read_json(receipt)
    require(_sha(_read(receipt, MAX_JSON)) == _sha(raw), 'approval receipt changed during read')
    expected = {'schema_version': 1, 'kind': 'trusted_design_approval',
                'decision': 'accepted', 'intent': INTENT, 'character_id': request['character_id'],
                'revision': gate['revision'], 'design_record_sha256': gate['record_sha256'],
                'review_basis_sha256': gate['review_basis_sha256'], 'reviewer': reviewer}
    keys(value, set(expected), set(), 'approval')
    require(type(value['schema_version']) is int and value == expected,
            'trusted approval receipt scope, revision, reviewer or binding mismatch')
    return _sha(raw)


def import_existing(concept: Path, sheet: Path, image: Path, packet: Path,
                    approval_directory: Path, pending_directory: Path, **identity) -> dict:
    root = _private_directory(pending_directory)
    require(root != approval_directory.resolve() and not root.is_relative_to(approval_directory.resolve())
            and not approval_directory.resolve().is_relative_to(root),
            'pending area and approval store must be separate')
    current, raw = _request(concept, sheet, image, **identity)
    request_bytes = _read(packet, MAX_JSON)
    require(request_bytes == canonical(current), 'stale or invalid import request; export current inputs again')
    receipt_sha = _approval(approval_directory, current, concept, sheet, image, packet)
    width, height, pixels = png.decode(raw)
    alpha = pixels[3::4]
    require(0 in alpha and any(alpha), 'portrait must contain both transparent and visible pixels')
    request_sha = _sha(request_bytes)
    summary = {'schema_version': 1, 'kind': 'pending_static_portrait_candidate',
               'review_status': 'pending', 'request_sha256': request_sha,
               'trusted_design_receipt_sha256': receipt_sha,
               'portrait': {'file': 'portrait.png', 'sha256': current['source_png_sha256'],
                            'width': width, 'height': height},
               'generated': False, 'final_art_approved': False, 'runtime_integrated': False}

    def write(handle):
        with zipfile.ZipFile(handle, mode='w', compression=zipfile.ZIP_STORED) as bundle:
            for name, data in (('portrait.png', raw), ('request.json', request_bytes),
                               ('candidate.json', canonical(summary))):
                entry = zipfile.ZipInfo(name)
                entry.external_attr = (stat.S_IFREG | 0o600) << 16
                bundle.writestr(entry, data)

    def revalidate():
        latest, _ = _request(concept, sheet, image, **identity)
        require(latest == current and _read(packet, MAX_JSON) == request_bytes,
                'inputs changed during import; no candidate published')
        require(_approval(approval_directory, latest, concept, sheet, image, packet) == receipt_sha,
                'approval changed during import; no candidate published')

    target = _publish(root, current['character_id'] + '-' + request_sha + '.pending.zip', write, revalidate)
    return {**summary, 'bundle': target.name}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('export-request', 'import-existing'):
        cmd = commands.add_parser(name)
        for arg in ('concept', 'design', 'portrait'):
            cmd.add_argument('--' + arg, required=True, type=Path)
        for arg in ('character-id', 'concept-revision', 'design-revision'):
            cmd.add_argument('--' + arg, required=True)
        if name == 'export-request':
            cmd.add_argument('--output', required=True, type=Path)
        else:
            cmd.add_argument('--request', required=True, type=Path)
            cmd.add_argument('--trusted-approval-directory', required=True, type=Path,
                             help='Caller-configured read-only trusted source; never let an applicant select this')
            cmd.add_argument('--pending-directory', required=True, type=Path)
    a = parser.parse_args()
    identity = {'character_id': a.character_id, 'concept_revision': a.concept_revision,
                'design_revision': a.design_revision}
    try:
        report = (export_request(a.concept, a.design, a.portrait, a.output, **identity)
                  if a.command == 'export-request' else
                  import_existing(a.concept, a.design, a.portrait, a.request,
                                  a.trusted_approval_directory, a.pending_directory, **identity))
    except (ArtError, OSError, ValueError, RecursionError) as error:
        parser.exit(1, f'Static portrait handoff blocked: {error}\n')
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
