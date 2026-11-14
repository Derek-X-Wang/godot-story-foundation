#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
"""Run optional idle lifecycle and motion with synthetic standalone dependencies."""
from pathlib import Path
import argparse
import os
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpu", action="store_true", help="Require a display and actual OpenGL renderer")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="foundation-idle-") as folder:
        base = Path(folder)
        env = os.environ.copy()
        for key in ("XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"):
            dest = base / key.lower()
            dest.mkdir()
            env[key] = str(dest)
        project = base / "relocated"
        for rel in ("addons/story_foundation/presentation/idle_host_adapter.gd",
                    "addons/story_foundation/presentation/portrait_idle_motion.gd",
                    "addons/story_foundation/presentation/portrait_idle_motion.gdshaderinc",
                    "tests/portrait_idle/gpu.gd",
                    "tests/portrait_idle/motion.gd", "tests/portrait_idle/test.gd"):
            target = project / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, target)
        (project / "project.godot").write_text('config_version=5\n')
        run_test(project, env, "test.gd", "PASS: 53 idle-host assertions")
        run_test(project, env, "motion.gd", "PASS: 169 portrait-motion assertions")

        if args.gpu:
            run_test(project, env, "gpu.gd", "PASS: 229 GPU portrait-motion assertions", gpu=True)

def run_test(project, env, script, marker, gpu=False):
    renderer = ["--rendering-method", "gl_compatibility", "--audio-driver", "Dummy"] if gpu else ["--headless"]
    result = subprocess.run([os.environ.get("GODOT", "godot"), *renderer,
        "--path", str(project), "--script", "res://tests/portrait_idle/" + script],
        env=env, capture_output=True, text=True, timeout=90)
    output = result.stdout + result.stderr
    print(output, end="")
    if result.returncode or any(line.lstrip().startswith(("ERROR:", "SCRIPT ERROR:"))
                               for line in output.splitlines()):
        raise SystemExit("Idle adapter engine test failed")
    if marker not in output:
        raise SystemExit("Idle adapter result missing or assertion count changed")

if __name__ == "__main__":
    main()
