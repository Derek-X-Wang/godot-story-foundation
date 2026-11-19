"""Exercise CI dependency decisions with fake package and display providers."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/prepare_ci_dependencies.sh"
STUB = r'''
import os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
root = pathlib.Path(os.environ["MOCK_BIN"])
mode = os.environ.get("MOCK_MODE", "")
if name == "dpkg-query":
    if args[-1] in ("libgl1-mesa-dri",) and mode != "missing-mesa":
        print("installed", end="")
    else:
        sys.exit(1)
elif name == "sudo":
    with pathlib.Path(os.environ["MOCK_LOG"]).open("a") as out:
        out.write(" ".join(args) + "\n")
    if "update" in args and mode == "apt-update-timeout":
        sys.exit(124)
    if "install" in args:
        if mode == "apt-install-timeout":
            sys.exit(124)
        for pkg, commands in {"ffmpeg": ("ffmpeg", "ffprobe"), "xvfb": ("xvfb-run", "Xvfb"),
                              "xauth": ("xauth",)}.items():
            if pkg in args:
                for command in commands:
                    path = root / command
                    if not path.exists():
                        path.symlink_to(root / "stub")
elif name == "ffmpeg":
    if mode == "ffmpeg-broken":
        sys.exit(8)
    pathlib.Path(args[-1]).write_bytes(b"audio fixture")
elif name == "ffprobe":
    if not pathlib.Path(args[-1]).exists():
        sys.exit(5)
    print("different_codec" if mode == "ffprobe-wrong-codec" else "pcm_s16le")
elif name == "xvfb-run":
    if mode == "xvfb-broken":
        sys.exit(4)
    assert args[:3] == ["-a", "-e", "/dev/stderr"]
    os.execvpe(args[3], args[3:], {**os.environ, "DISPLAY": ":104", "XAUTHORITY": "/mock/cookie"})
elif name == "xauth":
    if mode != "xauth-no-cookie":
        print("mock cookie")
elif name == "godot":
    assert os.environ["LIBGL_ALWAYS_SOFTWARE"] == "1"
    assert args[:6] == ["--display-driver", "x11", "--rendering-method",
                        "gl_compatibility", "--audio-driver", "Dummy"]
    assert pathlib.Path(args[7], "probe_ci_opengl.gd").is_file()
    if mode != "no-opengl":
        print("CI OpenGL ready: distinct backend, API 4.5")
    if mode == "dirty-opengl":
        print("  ERROR: simulated engine error")
'''


class CiDependencyPreflightTest(unittest.TestCase):
    def setUp(self):
        target = tempfile.TemporaryDirectory()
        self.addCleanup(target.cleanup)
        root = Path(target.name)
        self.bin = root / "bin"
        self.bin.mkdir()
        self.log = root / "sudo.log"
        self.env = dict(os.environ, PATH=str(self.bin), MOCK_BIN=str(self.bin), MOCK_LOG=str(self.log), GODOT="godot")
        (self.bin / "stub").write_text(f"#!{sys.executable}\n{STUB}")
        (self.bin / "stub").chmod(0o700)
        for command in ("bash", "cat", "cp", "dirname", "env", "grep", "mktemp", "rm", "timeout"):
            path = shutil.which(command)
            if not path:
                self.skipTest(f"Ubuntu shell dependency unavailable: {command}")
            (self.bin / command).symlink_to(path)
        for command in ("dpkg-query", "sudo", "ffmpeg", "ffprobe", "xvfb-run", "Xvfb", "xauth", "godot"):
            (self.bin / command).symlink_to(self.bin / "stub")

    def run_script(self, command="prepare-packages", mode=""):
        return subprocess.run([str(self.bin / "bash"), str(SCRIPT), command],
                              capture_output=True, text=True, timeout=12,
                              env={**self.env, "MOCK_MODE": mode})

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def assert_failure(self, result, reason):
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(reason, result.stderr)

    def test_installed_skips_apt_but_checks_audio_and_display(self):
        result = self.run_script()
        self.assert_success(result)
        for marker in ("skipping apt", "PCM smoke passed", "Xvfb/xauth startup passed"):
            self.assertIn(marker, result.stdout)
        self.assertFalse(self.log.exists())

    def test_only_missing_packages_in_bounded_apt(self):
        # Missing both ffmpeg commands still results in one package, and
        # the existing xvfb command plus a missing server requires xvfb.
        for cmd in ("ffmpeg", "ffprobe", "Xvfb"):
            (self.bin / cmd).unlink()
        self.assert_success(self.run_script())
        update, install = self.log.read_text().splitlines()
        self.assertIn("timeout -k 5s 90s apt-get ", update)
        self.assertTrue(update.endswith("APT::Update::Error-Mode=any update"))
        self.assertIn("Acquire::Retries=1", update)
        self.assertIn("timeout -k 5s 240s apt-get ", install)
        self.assertTrue(install.endswith("install --no-install-recommends -y ffmpeg xvfb"))

    def test_missing_mesa_package_does_not_reinstall_other_tools(self):
        self.assert_success(self.run_script(mode="missing-mesa"))
        self.assertTrue(self.log.read_text().splitlines()[-1].endswith("-y libgl1-mesa-dri"))

    def test_update_failure_does_not_try_install(self):
        (self.bin / "ffprobe").unlink()
        self.assert_failure(self.run_script(mode="apt-update-timeout"), "apt update failed")
        self.assertEqual(len(self.log.read_text().splitlines()), 1)

    def test_install_failure_does_not_claim_ready(self):
        (self.bin / "ffprobe").unlink()
        result = self.run_script(mode="apt-install-timeout")
        self.assert_failure(result, "apt install failed")
        self.assertNotIn("Ready:", result.stdout)

    def test_present_but_broken_probes_fail_without_apt(self):
        for mode, marker in (("ffmpeg-broken", "ffmpeg could not"), ("ffprobe-wrong-codec", "unexpected audio codec"),
                             ("xvfb-broken", "xvfb-run could not"), ("xauth-no-cookie", "xauth cookie")):
            with self.subTest(mode=mode):
                self.assert_failure(self.run_script(mode=mode), marker)
                self.assertFalse(self.log.exists())

    def test_renderer_uses_software_gl_request_and_accepts_unlisted_adapter(self):
        self.assert_success(self.run_script("probe-renderer"))
        self.assertFalse(self.log.exists())

    def test_renderer_rejects_no_context_or_engine_error(self):
        for mode in ("no-opengl", "dirty-opengl"):
            with self.subTest(mode=mode):
                self.assert_failure(self.run_script("probe-renderer", mode), "without a clean non-headless OpenGL")
                self.assertFalse(self.log.exists())


if __name__ == "__main__":
    unittest.main()
