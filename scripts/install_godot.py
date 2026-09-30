#!/usr/bin/env python3
"""Install the locked official Godot Linux x86_64 editor into .deps/godot.

No root permissions or global PATH changes. Use `.deps/godot --version` after
installation. Other platforms should install Godot 4.6.3 from godotengine.org.
"""

from __future__ import annotations

import os
from pathlib import Path
import platform
import sys
import tempfile
import zipfile

from fetch_dependencies import (
    ROOT, cache_dir, copy_member, fetch_verified, load_lock, safe_zip_members,
)


def install_godot(root: Path = ROOT) -> Path:
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "AMD64"):
        raise ValueError("This installer supports Linux x86_64 only; install Godot 4.6.3 for your OS")
    entry = load_lock(root)["godot"]
    deps = cache_dir(root)
    archive_path = fetch_verified(
        entry["url"], deps / "downloads" / f"Godot_v{entry['version']}_{entry['platform']}.zip",
        entry["sha256"], entry["max_download_bytes"], entry["sha512"])
    destination = deps / "godot"
    if destination.is_symlink():
        raise ValueError("Refusing a symlinked Godot destination")
    with tempfile.TemporaryDirectory(prefix=".godot-stage-", dir=deps) as staging:
        binary = Path(staging) / "godot"
        with zipfile.ZipFile(archive_path) as archive:
            members = safe_zip_members(archive, entry["max_unpacked_bytes"])
            selected = [info for info, path in members
                        if str(path) == entry["archive_member"] and not info.is_dir()]
            if len(selected) != 1:
                raise ValueError("Godot archive does not contain the locked executable")
            copy_member(archive, selected[0], binary)
        os.chmod(binary, 0o755)
        binary.replace(destination)
    return destination


def main() -> int:
    try:
        path = install_godot()
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        print(f"Godot installation failed: {error}", file=sys.stderr)
        return 1
    print(f"Verified Godot {load_lock()['godot']['version']}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
