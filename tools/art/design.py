"""Optional offline character-design provenance checks; no image/provider execution."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from .manifest import ArtError, canonical, digest, integer, keys, read_json, require, safe_name, source_path, text


def sha256(value: object, label: str) -> None:
    require(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None,
            f'{label}: lowercase SHA-256 required')


def file_record(value: object, label: str, reference: bool = False) -> None:
    keys(value, {'path', 'sha256'} | ({'role'} if reference else set()), set(), label)
    text(value['path'], f'{label}.path')
    sha256(value['sha256'], f'{label}.sha256')
    if reference:
        safe_name(value['role'], f'{label}.role')


def review_basis(record: dict) -> str:
    """Bind the declared review to every non-review field, including limitations."""
    return hashlib.sha256(canonical({k: v for k, v in record.items() if k != 'review'})).hexdigest()


def validate_record(record: object) -> None:
    keys(record, {'schema_version', 'kind', 'character', 'stage', 'references',
                  'producer', 'output', 'limitations', 'review'}, {'capture'}, 'design')
    integer(record['schema_version'], 1, 1, 'schema_version')
    require(record['kind'] == 'character_design', 'kind: character_design required')
    keys(record['character'], {'id', 'revision'}, set(), 'character')
    safe_name(record['character']['id'], 'character.id')
    text(record['character']['revision'], 'character.revision')
    require(record['stage'] in ('concept', 'design', 'pose_study'), 'stage: unsupported design stage')
    references = record['references']
    require(isinstance(references, list) and len(references) <= 32, 'references: list of at most 32 required')
    for index, reference in enumerate(references):
        file_record(reference, f'references[{index}]', reference=True)
    file_record(record['output'], 'output')
    producer = record['producer']
    keys(producer, {'name', 'version'}, {'model', 'work'}, 'producer')
    for field in ('name', 'version'):
        text(producer[field], f'producer.{field}')
    for field in ('model', 'work'):
        if field in producer:
            keys(producer[field], {'id', 'revision'}, set(), f'producer.{field}')
            for key in ('id', 'revision'):
                text(producer[field][key], f'producer.{field}.{key}')
    if 'capture' in record:
        keys(record['capture'], set(), {'camera', 'pose'}, 'capture')
        require(bool(record['capture']), 'capture: omit when unavailable')
        for field, value in record['capture'].items():
            text(value, f'capture.{field}')
    require(isinstance(record['limitations'], list) and 1 <= len(record['limitations']) <= 32,
            'limitations: list of 1..32 explicit statements required')
    for limitation in record['limitations']:
        text(limitation, 'limitations[]')
    review = record['review']
    keys(review, {'status', 'reviewer', 'notes', 'basis_sha256'}, set(), 'review')
    require(review['status'] in ('pending', 'accepted', 'rejected'), 'review.status: unsupported status')
    text(review['notes'], 'review.notes')
    if review['status'] == 'pending':
        require(review['reviewer'] is None and review['basis_sha256'] is None,
                'pending review: reviewer and basis_sha256 must be null')
    else:
        text(review['reviewer'], 'review.reviewer')
        sha256(review['basis_sha256'], 'review.basis_sha256')
        require(review['basis_sha256'] == review_basis(record), 'review: stale basis; a new human review is required')


def check(path: Path, *, character_id: str, revision: str,
          expected_record_sha256: str | None = None) -> dict:
    """Compare caller expectations and local bytes. Never mutate or approve a record."""
    safe_name(character_id, 'expected character_id')
    text(revision, 'expected revision')
    record = read_json(path)
    validate_record(record)
    require(record['character'] == {'id': character_id, 'revision': revision},
            'character identity/revision does not match caller expectation')
    record_hash = digest(path)
    if expected_record_sha256 is not None:
        sha256(expected_record_sha256, 'expected_record_sha256')
        require(record_hash == expected_record_sha256, 'record SHA-256 does not match independent expectation')
    resolved = set()
    for label, item in [(f'references[{i}]', ref) for i, ref in enumerate(record['references'])] + [('output', record['output'])]:
        try:
            local = source_path(path, item)
        except (ArtError, OSError, ValueError) as error:
            raise ArtError(f'{label}: {error}') from error
        require(local.resolve() not in resolved, f'{label}: duplicate reference/output file')
        resolved.add(local.resolve())
    require(digest(path) == record_hash, 'record changed during validation')
    return {
        'schema_version': 1,
        'check': 'local_design_provenance',
        'character': record['character'],
        'stage': record['stage'],
        'record_sha256': record_hash,
        'record_matches_independent_expectation': expected_record_sha256 is not None,
        'local_file_hashes_match': True,
        'review_basis_sha256': review_basis(record),
        'declared_human_review_status': record['review']['status'],
        'art_approval': 'not_determined_by_tool',
        'integration_approval': 'not_determined_by_tool',
        'semantic_correctness': 'not_verified',
        'remote_persistence': 'not_verified',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path)
    parser.add_argument('--character-id', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--expected-record-sha256', help='Previously retained independent record digest, not one derived to make this check pass')
    args = parser.parse_args()
    try:
        report = check(args.record, character_id=args.character_id, revision=args.revision,
                       expected_record_sha256=args.expected_record_sha256)
    except (ArtError, OSError, ValueError) as error:
        print(f'Design provenance failed: {error}', file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
