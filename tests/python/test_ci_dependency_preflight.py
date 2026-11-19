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
import os, pathlib, shutil, stat, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
root = pathlib.Path(os.environ["MOCK_BIN"])
mode = os.environ.get("MOCK_MODE", "")
if name == "dpkg-query":
    if args[-1] in ("libgl1-mesa-dri",) and mode != "missing-mesa":
        print("installed", end="")
    else:
        sys.exit(1)
elif name == "lsb_release":
    print(("Debian" if mode == "wrong-os" else "Ubuntu") if args == ["-is"] else "noble")
elif name == "dpkg":
    assert args == ["--print-architecture"]
    print("arm64" if mode == "wrong-architecture" else "amd64")
elif name == "sudo":
    assert args[0] == "-n"
    with pathlib.Path(os.environ["MOCK_ALL_SUDO"]).open("a") as out:
        out.write(" ".join(args) + "\n")
    if args[1:3] == ["rm", "-rf"]:
        assert args[3] == "--"
        shutil.rmtree(args[4])
        sys.exit(0)
    if args[1:3] == ["install", "-d"]:
        assert args[3] == "-o" and args[5:8] == ["-g", "root", "-m"]
        assert (args[4], args[8]) in {("root", "0755"), ("_apt", "0700")}
        for d in args[9:]:
            pathlib.Path(d).mkdir(mode=int(args[8], 8), parents=True)
        sys.exit(0)
    if args[1:5] == ["-u", "_apt", "sh", "-ec"]:
        tmp = pathlib.Path(args[-1])
        assert stat.S_IMODE(tmp.stat().st_mode) == 0o755
        assert stat.S_IMODE((tmp / "sources.d/ubuntu.sources").stat().st_mode) == 0o644
        assert stat.S_IMODE((tmp / "lists/partial").stat().st_mode) == 0o700
        assert stat.S_IMODE((tmp / "archives/partial").stat().st_mode) == 0o700
        sys.exit(1 if mode == "apt-permissions" else 0)
    assert "apt-get" in args
    with pathlib.Path(os.environ["MOCK_LOG"]).open("a") as out:
        out.write(" ".join(args) + "\n")
    if "update" in args:
        p = next(a.split("=", 1)[1] for a in args if a.startswith("Dir::Etc::sourceparts="))
        shutil.copyfile(pathlib.Path(p, "ubuntu.sources"), os.environ["MOCK_SOURCES"])
        if mode == "apt-unsandboxed-warning":
            print("W: Download is performed unsandboxed as root", file=sys.stderr)
        if mode in ("apt-update-timeout", "apt-bad-signature"):
            sys.exit(124 if mode == "apt-update-timeout" else 100)
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
        self.sudo = root / "all-sudo.log"
        self.sources = root / "sources.txt"
        self.env = dict(os.environ, PATH=str(self.bin), MOCK_BIN=str(self.bin),
                        MOCK_LOG=str(self.log), GODOT="godot", MOCK_ALL_SUDO=str(self.sudo),
                        MOCK_SOURCES=str(self.sources))
        (self.bin / "stub").write_text(f"#!{sys.executable}\n{STUB}")
        (self.bin / "stub").chmod(0o700)
        for command in ("bash", "cat", "chmod", "cp", "dirname", "env", "grep", "mkdir", "mktemp", "rm", "tee", "timeout"):
            path = shutil.which(command)
            if not path:
                self.skipTest(f"Ubuntu shell dependency unavailable: {command}")
            (self.bin / command).symlink_to(path)
        for command in ("dpkg", "dpkg-query", "lsb_release", "sudo", "ffmpeg", "ffprobe", "xvfb-run", "Xvfb", "xauth", "godot"):
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
        self.assertFalse(self.sudo.exists())
        self.assertFalse(self.sources.exists())

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
        for cmd in (update, install):
            for option in ("Dir::Etc::sourcelist=/dev/null", "APT::Sandbox::User=_apt",
                           "APT::Get::AllowUnauthenticated=false", "Acquire::AllowInsecureRepositories=false",
                           "Acquire::https::Verify-Peer=true", "Acquire::https::Verify-Host=true",
                           "Acquire::https::AllowRedirect=false", "Acquire::Languages=none"):
                self.assertIn(option, cmd)
            self.assertRegex(cmd, r"Dir::Etc::sourceparts=/tmp/foundation-ci-apt\.[^ ]+/sources.d")
            self.assertRegex(cmd, r"Dir::State::lists=/tmp/foundation-ci-apt\.[^ ]+/lists")
            self.assertRegex(cmd, r"Dir::Cache::archives=/tmp/foundation-ci-apt\.[^ ]+/archives")
        sources = self.sources.read_text()
        self.assertEqual([line for line in sources.splitlines() if line.startswith("URIs:")],
                         ["URIs: https://archive.ubuntu.com/ubuntu/", "URIs: https://security.ubuntu.com/ubuntu/"])
        self.assertEqual([line for line in sources.splitlines() if line.startswith("Suites:")],
                         ["Suites: noble noble-updates noble-backports", "Suites: noble-security"])
        self.assertEqual(sources.count("Components: main restricted universe multiverse"), 2)
        self.assertEqual(sources.count("Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg"), 2)
        apt_root = Path(self.sudo.read_text().splitlines()[-1].split()[-1])
        self.assertFalse(apt_root.exists())

    def test_wrong_platform_does_not_invoke_apt_or_sudo(self):
        (self.bin / "ffprobe").unlink()
        for mode in ("wrong-os", "wrong-architecture"):
            with self.subTest(mode=mode):
                self.assert_failure(self.run_script(mode=mode), "supports Ubuntu Noble amd64 only")
                self.assertFalse(self.sudo.exists())

    def test_apt_permissions_gate_precedes_network(self):
        (self.bin / "ffprobe").unlink()
        self.assert_failure(self.run_script(mode="apt-permissions"), "inaccessible to _apt")
        self.assertFalse(self.log.exists())
        self.assertFalse(self.sources.exists())

    def test_signature_failure_does_not_install_or_fall_back(self):
        (self.bin / "ffprobe").unlink()
        self.assert_failure(self.run_script(mode="apt-bad-signature"), "apt update failed")
        self.assertEqual(len(self.log.read_text().splitlines()), 1)


    def test_loss_of_apt_sandbox_stops_before_install(self):
        (self.bin / "ffprobe").unlink()
        self.assert_failure(self.run_script(mode="apt-unsandboxed-warning"), "lost the _apt download sandbox")
        self.assertEqual(len(self.log.read_text().splitlines()), 1)

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
