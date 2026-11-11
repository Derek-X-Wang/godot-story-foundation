#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
"""Run the optional idle driver with only synthetic standalone dependencies."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    with tempfile.TemporaryDirectory(prefix="foundation-idle-") as folder:
        base = Path(folder)
        env = os.environ.copy()
        for key in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
            dest = base / key.lower()
            dest.mkdir()
            env[key] = str(dest)
        project = base / "relocated"
        for rel in ("addons/story_foundation/presentation/idle_host_adapter.gd",
                    "tests/portrait_idle/test.gd"):
            target = project / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, target)
        (project / "project.godot").write_text('config_version=5\n')
        result = subprocess.run([os.environ.get("GODOT", "godot"), "--headless",
            "--path", str(project), "--script", "res://tests/portrait_idle/test.gd"],
            env=env, capture_output=True, text=True, timeout=90)
        output = result.stdout + result.stderr
        print(output, end="")
        if result.returncode or any(line.lstrip().startswith(("ERROR:", "SCRIPT ERROR:"))
                                   for line in output.splitlines()):
            raise SystemExit("Idle adapter engine test failed")
        if "PASS: 53 idle-host assertions" not in output:
            raise SystemExit("Idle adapter result missing or assertion count changed")

if __name__ == "__main__":
    main()
