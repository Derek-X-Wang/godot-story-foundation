#!/usr/bin/env python3
"""Stage the standalone neutral layered portrait tests; no external art or deps."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    with tempfile.TemporaryDirectory(prefix="foundation-portrait-") as temp:
        project = Path(temp)
        presentation = project / "addons/story_foundation/presentation"
        shutil.copytree(ROOT / "addons/story_foundation/presentation", presentation)
        shutil.copy2(ROOT / "tests/presentation/test_registered_portrait.gd", project / "test.gd")
        (project / "project.godot").write_text(
            'config_version=5\n[application]\nconfig/name="Neutral Portrait Test"\n'
            '[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
        )
        env = dict(os.environ, XDG_DATA_HOME=str(project / "data"),
                   XDG_CONFIG_HOME=str(project / "config"), XDG_CACHE_HOME=str(project / "cache"))
        return subprocess.run([os.environ.get("GODOT", "godot"), "--headless", "--path", str(project),
                               "--script", "test.gd"], env=env, check=False).returncode

if __name__ == "__main__":
    raise SystemExit(main())
