#!/usr/bin/env python3
"""Fetch the locked official Dialogue Manager addon, without vendoring its repo.

Only Python's standard library is needed. Cached archives are reverified on
every run. A failed checksum is an error, never a reason to use existing files.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CHUNK_BYTES = 1024 * 1024
MAX_ZIP_MEMBERS = 10000


def load_lock(root: Path = ROOT) -> dict:
    lock = json.loads((root / "deps.lock.json").read_text(encoding="utf-8"))
    if lock.get("schema_version") != 1:
        raise ValueError("Unsupported dependency lock schema")
    return lock


def cache_dir(root: Path = ROOT) -> Path:
    directory = root / ".deps"
    if directory.is_symlink():
        raise ValueError("Refusing a symlinked .deps directory")
    directory.mkdir(exist_ok=True)
    return directory


def verify_archive(path: Path, sha256: str, max_bytes: int,
                   sha512: str | None = None) -> None:
    if not re.fullmatch(r"[a-f0-9]{64}", sha256):
        raise ValueError("The lock must contain a full SHA-256 digest")
    if sha512 is not None and not re.fullmatch(r"[a-f0-9]{128}", sha512):
        raise ValueError("The lock must contain a full SHA-512 digest")
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Not a regular archive: {path}")
    if path.stat().st_size > max_bytes:
        raise ValueError(f"Archive exceeds download limit: {path.name}")
    h256, h512 = hashlib.sha256(), hashlib.sha512()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_BYTES), b""):
            h256.update(chunk)
            h512.update(chunk)
    if h256.hexdigest() != sha256:
        raise ValueError(f"SHA-256 mismatch for {path.name}; refusing archive")
    if sha512 is not None and h512.hexdigest() != sha512:
        raise ValueError(f"SHA-512 mismatch for {path.name}; refusing archive")


def fetch_verified(url: str, destination: Path, sha256: str, max_bytes: int,
                   sha512: str | None = None) -> Path:
    """Download bounded HTTPS bytes, then verify before promoting to cache."""
    if urlparse(url).scheme != "https":
        raise ValueError("Dependency downloads require HTTPS")
    if max_bytes <= 0:
        raise ValueError("Download limit must be positive")
    if destination.is_symlink() or destination.parent.is_symlink():
        raise ValueError("Refusing a symlinked archive cache")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        verify_archive(destination, sha256, max_bytes, sha512)
        return destination
    fd, name = tempfile.mkstemp(prefix=".download-", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as output:
            request = Request(url, headers={"User-Agent": "godot-story-foundation/0.1"})
            with urlopen(request, timeout=90) as response:
                if urlparse(response.geturl()).scheme != "https":
                    raise ValueError("Refusing an insecure download redirect")
                length = response.headers.get("Content-Length")
                if length is not None and int(length) > max_bytes:
                    raise ValueError("Download exceeds locked size limit")
                total = 0
                while chunk := response.read(CHUNK_BYTES):
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("Download exceeds locked size limit")
                    output.write(chunk)
        verify_archive(temporary, sha256, max_bytes, sha512)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def safe_zip_members(archive: zipfile.ZipFile, max_unpacked_bytes: int
                     ) -> list[tuple[zipfile.ZipInfo, PurePosixPath]]:
    """Validate the whole archive before writing any members (no extractall)."""
    members = archive.infolist()
    if len(members) > MAX_ZIP_MEMBERS:
        raise ValueError("Too many ZIP members")
    expanded = 0
    seen: set[str] = set()
    result = []
    for info in members:
        name = info.filename
        parts = name.rstrip("/").split("/")
        if (not name or "\\" in name or ":" in name or "\x00" in name
                or name.startswith("/") or any(p in ("", ".", "..") for p in parts)):
            raise ValueError(f"Unsafe ZIP path: {name!r}")
        path = PurePosixPath(*parts)
        key = str(path).casefold()
        if key in seen:
            raise ValueError(f"Duplicate ZIP path: {name}")
        seen.add(key)
        kind = stat.S_IFMT(info.external_attr >> 16)
        if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise ValueError(f"Refusing symlink or special ZIP member: {name}")
        if info.flag_bits & 1:
            raise ValueError(f"Refusing encrypted ZIP member: {name}")
        expanded += info.file_size
        if info.file_size < 0 or expanded > max_unpacked_bytes:
            raise ValueError("ZIP exceeds unpacked size limit")
        result.append((info, path))
    return result


def copy_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    # Stream instead of allocating an entire untrusted member in memory.
    with archive.open(info) as source, target.open("xb") as output:
        shutil.copyfileobj(source, output, CHUNK_BYTES)


def install_dialogue_manager(root: Path = ROOT) -> Path:
    entry = load_lock(root)["dialogue_manager"]
    commit = entry["commit"]
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        raise ValueError("Dialogue Manager must be pinned to a full commit")
    deps = cache_dir(root)
    archive_path = fetch_verified(
        entry["url"], deps / "downloads" / f"dialogue-manager-{commit}.zip",
        entry["sha256"], entry["max_download_bytes"])
    destination = deps / "dialogue_manager"
    if destination.is_symlink():
        raise ValueError("Refusing a symlinked addon destination")
    prefix = PurePosixPath(entry["archive_prefix"])
    with tempfile.TemporaryDirectory(prefix=".dialogue-stage-", dir=deps) as staging:
        stage = Path(staging) / "dialogue_manager"
        stage.mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            for info, path in safe_zip_members(archive, entry["max_unpacked_bytes"]):
                if info.is_dir() or not path.is_relative_to(prefix):
                    continue
                relative = path.relative_to(prefix)
                if not relative.parts:
                    raise ValueError("Addon prefix names a file")
                copy_member(archive, info, stage.joinpath(*relative.parts))
        for required in ("LICENSE", "plugin.cfg", "dialogue_manager.gd"):
            if not (stage / required).is_file():
                raise ValueError(f"Locked archive is missing {required}")
        if (stage / "LICENSE").read_bytes() != (root / entry["license_file"]).read_bytes():
            raise ValueError("Upstream license differs from reviewed license copy")
        backup = Path(staging) / "previous"
        if destination.exists():
            destination.rename(backup)
        try:
            stage.rename(destination)
        except BaseException:
            if backup.exists():
                backup.rename(destination)
            raise
    return destination


def main() -> int:
    try:
        path = install_dialogue_manager()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(f"Dependency bootstrap failed: {error}", file=sys.stderr)
        return 1
    print(f"Verified Dialogue Manager {load_lock()['dialogue_manager']['version']}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
