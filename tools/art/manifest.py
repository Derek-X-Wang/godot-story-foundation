"""Small shared asset identity/provenance contract and local source boundary."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re


class ArtError(ValueError):
    """Actionable validation or adapter failure; no output is promoted."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ArtError(message)


def keys(value: object, required: set[str], optional: set[str], label: str) -> None:
    require(isinstance(value, dict), f'{label}: expected object')
    require(required <= value.keys(), f'{label}: missing {sorted(required - value.keys())}')
    require(not value.keys() - required - optional,
            f'{label}: unknown fields {sorted(value.keys() - required - optional)}')


def integer(value: object, low: int, high: int, label: str) -> None:
    require(type(value) is int and low <= value <= high, f'{label}: integer {low}..{high} required')


def text(value: object, label: str) -> None:
    require(isinstance(value, str) and bool(value.strip()) and len(value) <= 4096,
            f'{label}: non-empty text required (max 4096 characters)')


def safe_name(value: object, label: str) -> None:
    require(isinstance(value, str) and re.fullmatch(r'[a-z][a-z0-9_]{0,63}', value) is not None,
            f'{label}: lowercase identifier required')


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode()


def read_json(path: Path) -> dict:
    require(path.stat().st_size <= 1_048_576, 'JSON exceeds 1 MiB')
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, f'duplicate JSON field: {k}')
            result[k] = v
        return result
    try:
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ArtError(f'invalid JSON: {error}') from error


def validate_provenance(value: object, allow_unknown: bool = False) -> list[str]:
    keys(value, {'origin', 'creator', 'license', 'rights', 'notes'}, set(), 'provenance')
    require(value['origin'] in ('original', 'ai_assisted', 'licensed', 'unknown'),
            'provenance.origin: unsupported origin')
    for field in ('creator', 'license', 'notes'):
        text(value[field], f'provenance.{field}')
    require(value['rights'] in ('recorded', 'unknown'), 'provenance.rights: recorded or unknown required')
    unknown = (value['origin'] == 'unknown' or value['rights'] == 'unknown'
               or value['license'].strip().lower() in ('unknown', 'tbd', 'none'))
    require(not unknown or allow_unknown,
            'unknown provenance/license: record rights, or use --allow-unknown-provenance for an exploratory build')
    return ['UNKNOWN_PROVENANCE: exploratory output; not cleared for distribution'] if unknown else []


def source_path(manifest_path: Path, source: dict) -> Path:
    name = source['path']
    text(name, 'source.path')
    require('\\' not in name and ':' not in name and not Path(name).is_absolute()
            and all(p not in ('', '.', '..') for p in name.split('/')),
            'source.path: use a relative file beneath the manifest directory')
    root = manifest_path.parent.resolve()
    path = root / name
    require(path.is_file() and path.resolve().is_relative_to(root), 'source.path: missing file or escaped directory')
    require(path.stat().st_size <= 64 * 1024 * 1024, 'source file exceeds 64 MiB')
    require(digest(path) == source['sha256'], 'source SHA-256 mismatch; review changed source and update manifest')
    return path
