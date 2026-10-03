"""Neutral fixture tests; no game content or engine dependency."""

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools.impact.selector import ContractError, load_manifest, select, validate_manifest


def manifest():
    return {
        "schema_version": 1,
        "components": [
            {"id": "audio", "paths": ["scripts/audio.gd", "assets/audio/**"]},
            {"id": "gain", "paths": [], "depends_on": ["audio"]},
            {"id": "core", "paths": ["backend/**"]},
            {"id": "save", "paths": ["save/**"], "depends_on": ["core"]},
            {"id": "story", "paths": ["story/**"], "depends_on": ["core"]},
            {"id": "tools", "paths": ["docs/**", "tools/**", "generated/**", "security/**"]},
        ],
        "suites": [
            {"id": "integrity", "components": [], "always": True, "command": ["python3", "check.py"]},
            {"id": "prepare", "components": [], "command": ["python3", "prepare.py"]},
            {"id": "gain", "components": ["gain"], "depends_on": ["prepare"], "command": ["python3", "gain.py"]},
            {"id": "audio", "components": ["audio"], "command": ["python3", "audio.py"]},
            {"id": "save", "components": ["save"], "command": ["python3", "save.py"]},
            {"id": "story", "components": ["story"], "command": ["python3", "story.py"]},
            {"id": "tools", "components": ["tools"], "command": ["python3", "tools.py"]},
        ],
        "content_rules": [{"path": "scripts/audio.gd", "components": ["gain"], "constants": {
            "EFFECT_GAIN_DB": {"min": -80, "max": 12},
            "MUSIC_GAIN_DB": {"min": -80, "max": 12},
        }}],
        "generated_paths": ["generated/**"],
        "guard_paths": ["security/**"],
    }


AUDIO = ('extends Node\nconst EFFECT_GAIN_DB: float = -12.0\n'
         'const MUSIC_GAIN_DB := -8.0\n\n'
         'func output_bus():\n    return "NeutralEffects"\n')


class SelectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "neutral@example.invalid")
        self.git("config", "user.name", "Neutral Fixture")
        self.write(".gitignore", "ignored/\n")
        self.write("scripts/audio.gd", AUDIO)
        self.write("backend/kernel.gd", "extends RefCounted\n")
        self.write("save/schema.json", '{"version":1}\n')
        self.write("story/neutral.json", '{"label":"Neutral gate"}\n')
        self.write("docs/tool.md", "Neutral instructions.\n")
        self.write("tools/check.py", "print('neutral')\n")
        self.base = self.commit()
        self.config = manifest()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], stderr=subprocess.STDOUT).decode().strip()

    def write(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            target.write_bytes(data)
        else:
            target.write_text(data, encoding="utf-8")

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "Neutral fixture snapshot")
        return self.git("rev-parse", "HEAD")

    def report(self, **kwargs):
        return select(self.root, self.base, "HEAD", self.config, **kwargs)

    def audio_edit(self, source):
        self.write("scripts/audio.gd", source)
        self.commit()
        return self.report()

    def test_numeric_only_narrows_and_prerequisites_precede(self):
        report = self.audio_edit(AUDIO.replace("-12.0", "-10.5"))
        self.assertEqual(report["direct_components"], ["gain"])
        self.assertEqual(report["component_closure"], ["gain"])
        self.assertEqual(report["selected_suite_ids"], ["integrity", "prepare", "gain"])
        self.assertEqual(report["changes"][0]["classification"], "bounded_numeric_constants")
        self.assertEqual(report["changes"][0]["constants"]["EFFECT_GAIN_DB"], {"old": "-12.0", "new": "-10.5"})
        self.assertFalse(report["passed"])
        self.assertFalse(report["complete"])
        self.assertEqual({s["status"] for s in report["skipped"]}, {"not_claimed"})

    def test_backend_edit_is_broad_audio_but_not_story_or_save(self):
        report = self.audio_edit(AUDIO.replace('"NeutralEffects"', '"NeutralMaster"'))
        self.assertEqual(report["component_closure"], ["audio", "gain"])
        self.assertEqual(set(report["selected_suite_ids"]), {"integrity", "prepare", "gain", "audio"})

    def test_core_reverse_dependencies_select_story_and_save(self):
        self.write("backend/kernel.gd", "extends Node\n")
        self.commit()
        self.assertEqual(self.report()["component_closure"], ["core", "save", "story"])
        self.assertEqual(set(self.report()["selected_suite_ids"]), {"integrity", "save", "story"})

    def test_expression_new_symbol_and_collateral_edits_cannot_narrow(self):
        mutations = [
            AUDIO.replace("-12.0", "-12.0 + 2.0"),
            AUDIO.replace("-12.0", "INF"),
            AUDIO.replace("-12.0", "1e9999"),
            AUDIO.replace("-12.0", "-81"),
            AUDIO.replace("-12.0", "true"),
            AUDIO.replace("-12.0", '"-10"'),
            AUDIO.replace("-12.0", "-10.0") + "const NEW_GAIN = 2.0\n",
            AUDIO.replace("-12.0", "-10.0").replace("NeutralEffects", "NeutralMaster"),
            AUDIO.replace("-12.0", "-10.0") + "# Updated documentation\n",
            AUDIO.replace("-12.0", "-10.0").replace("const MUSIC_GAIN_DB", "const OTHER_GAIN_DB"),
            AUDIO.replace("-12.0", "-10.0") + "const EFFECT_GAIN_DB = -8.0\n",
        ]
        for source in mutations:
            with self.subTest(source=source):
                report = self.audio_edit(source)
                self.assertEqual(report["changes"][0]["classification"], "path")
                self.assertIn("audio", report["selected_suite_ids"])

    def test_declaration_text_inside_string_cannot_narrow(self):
        for quote in ('"""', "'''"):
            original = "var text = " + quote + "\n" + AUDIO + quote + "\n"
            self.write("scripts/audio.gd", original)
            self.base = self.commit()
            report = self.audio_edit(original.replace("-12.0", "-10.0"))
            self.assertEqual(report["changes"][0]["classification"], "path")

    def test_comments_with_similar_declarations_remain_unchanged(self):
        original = AUDIO + "# const EFFECT_GAIN_DB = -1.0\n"
        self.write("scripts/audio.gd", original)
        self.base = self.commit()
        report = self.audio_edit(original.replace("-12.0", "-10.0"))
        self.assertEqual(report["changes"][0]["classification"], "bounded_numeric_constants")

    def test_nonutf8_and_binary_files_do_not_narrow(self):
        for suffix in (b"\0", b"\xff"):
            self.write("scripts/audio.gd", AUDIO.encode() + suffix)
            self.base = self.commit()
            report = self.audio_edit(AUDIO.replace("-12.0", "-10.0").encode() + suffix)
            self.assertEqual(report["changes"][0]["classification"], "path")

    def test_docs_and_known_tools_select_only_tooling_and_always(self):
        self.write("docs/tool.md", "Revised neutral instructions.\n")
        self.write("tools/check.py", "print('new neutral tool')\n")
        self.commit()
        report = self.report()
        self.assertEqual(set(report["selected_suite_ids"]), {"integrity", "tools"})
        self.assertFalse(report["conservative_reasons"])

    def test_unmapped_generated_and_guard_paths_force_all(self):
        for path, expected in (("unknown/new.gd", "unmapped"), ("generated/result.txt", "generated"),
                               ("security/checkpoint.json", "guard")):
            with self.subTest(path=path):
                self.write(path, "neutral\n")
                self.commit()
                report = self.report()
                self.assertEqual(set(report["selected_suite_ids"]), {s["id"] for s in self.config["suites"]})
                self.assertTrue(any(expected in reason for reason in report["conservative_reasons"]))

    def test_added_deleted_and_renamed_paths_hash_exact_bytes(self):
        os.rename(self.root / "backend/kernel.gd", self.root / "backend/renamed.gd")
        (self.root / "save/schema.json").unlink()
        self.write("story/new.json", '{"label":"Another neutral gate"}\n')
        head = self.commit()
        report = self.report()
        renamed = next(c for c in report["changes"] if c["status"].startswith("R"))
        self.assertEqual(renamed["old_path"], "backend/kernel.gd")
        self.assertEqual(renamed["new_path"], "backend/renamed.gd")
        self.assertEqual(renamed["old_sha256"], hashlib.sha256(b"extends RefCounted\n").hexdigest())
        self.assertEqual(renamed["old_sha256"], renamed["new_sha256"])
        deleted = next(c for c in report["changes"] if c["status"] == "D")
        added = next(c for c in report["changes"] if c["status"] == "A")
        self.assertIsNone(deleted["new_sha256"])
        self.assertIsNone(added["old_sha256"])
        self.assertEqual(report["base"]["commit"], self.base)
        self.assertEqual(report["head"]["commit"], head)
        self.assertEqual(report["head"]["tree"], self.git("rev-parse", "HEAD^{tree}"))
        self.assertIn("story", report["selected_suite_ids"])
        self.assertIn("save", report["selected_suite_ids"])

    def test_renamed_scalar_is_never_narrowed(self):
        os.rename(self.root / "scripts/audio.gd", self.root / "scripts/renamed.gd")
        self.commit()
        report = self.report()
        self.assertTrue(report["changes"][0]["status"].startswith("R"))
        self.assertEqual(report["changes"][0]["classification"], "conservative")

    @unittest.skipUnless(os.name == "posix", "POSIX executable modes")
    def test_mode_change_is_broad_even_with_scalar_change(self):
        self.write("scripts/audio.gd", AUDIO.replace("-12.0", "-10.0"))
        (self.root / "scripts/audio.gd").chmod(0o755)
        self.commit()
        self.assertEqual(self.report()["changes"][0]["classification"], "path")

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlink_change_is_conservative(self):
        os.symlink("../story/neutral.json", self.root / "backend/link")
        self.commit()
        report = self.report()
        self.assertIn("nonregular Git entry", report["conservative_reasons"])

    def test_gitlink_change_cannot_be_hidden_by_diff_configuration(self):
        # Synthetic commit objects suffice; no clone, network, or submodule
        # initialization is needed to exercise the superproject boundary.
        path = "backend/module"
        (self.root / path).mkdir()
        old_target = self.base
        self.git("update-index", "--add", "--cacheinfo", "160000," + old_target + "," + path)
        self.git("commit", "-q", "-m", "Neutral initial gitlink")
        self.base = self.git("rev-parse", "HEAD")
        new_target = self.base
        self.git("update-index", "--cacheinfo", "160000," + new_target + "," + path)
        self.git("commit", "-q", "-m", "Neutral changed gitlink")
        self.git("config", "diff.ignoreSubmodules", "all")
        self.assertEqual(self.git("diff", "--raw", self.base, "HEAD"), "")
        report = self.report()
        self.assertEqual(len(report["changes"]), 1)
        change = report["changes"][0]
        self.assertEqual(change["old_path"], path)
        self.assertEqual(change["new_path"], path)
        self.assertEqual(change["old_blob"], old_target)
        self.assertEqual(change["new_blob"], new_target)
        self.assertEqual(change["old_mode"], "160000")
        self.assertEqual(change["new_mode"], "160000")
        self.assertIsNone(change["old_sha256"])
        self.assertIsNone(change["new_sha256"])
        self.assertIn("nonregular Git entry", report["conservative_reasons"])
        self.assertEqual(set(report["selected_suite_ids"]), {s["id"] for s in self.config["suites"]})

    def test_tracked_staged_and_untracked_dirty_rejected(self):
        self.write("scripts/audio.gd", AUDIO.replace("-12.0", "-10.0"))
        with self.assertRaises(ContractError):
            self.report()
        self.git("add", "scripts/audio.gd")
        with self.assertRaises(ContractError):
            self.report()
        self.commit()
        self.write("new_source.py", "pass\n")
        with self.assertRaises(ContractError):
            self.report()

    def test_assume_unchanged_does_not_hide_dirty_source(self):
        self.git("update-index", "--assume-unchanged", "scripts/audio.gd")
        self.write("scripts/audio.gd", AUDIO.replace("-12.0", "-10.0"))
        with self.assertRaisesRegex(ContractError, "tracked checkout bytes"):
            self.report()

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlinked_parent_cannot_certify_outside_source(self):
        self.git("update-index", "--assume-unchanged", "scripts/audio.gd")
        outside = Path(self.temp.name) / "outside"
        shutil.move(str(self.root / "scripts"), outside)
        os.symlink(outside, self.root / "scripts")
        with self.assertRaises(ContractError):
            self.report()

    def test_ignored_output_allowed_but_not_claimed_as_source(self):
        self.write("ignored/report.json", "{}")
        report = self.report()
        self.assertEqual(report["changes"], [])
        self.assertEqual(report["selected_suite_ids"], ["integrity"])

    def test_historical_head_wrong_root_or_missing_ref_rejected(self):
        self.audio_edit(AUDIO.replace("-12.0", "-10.0"))
        with self.assertRaisesRegex(ContractError, "current HEAD"):
            select(self.root, self.base, self.base, self.config)
        with self.assertRaisesRegex(ContractError, "top-level"):
            select(self.root / "scripts", self.base, "HEAD", self.config)
        for ref in (None, "", "--all", "definitely-missing-ref"):
            with self.assertRaises(ContractError):
                select(self.root, ref, "HEAD", self.config)

    def test_full_and_missing_commands_never_pass(self):
        del self.config["suites"][3]["command"]
        report = self.report(full=True)
        self.assertEqual(len(report["selected"]), len(self.config["suites"]))
        self.assertEqual(report["skipped"], [])
        self.assertEqual(next(s for s in report["selected"] if s["id"] == "audio")["status"], "blocked")
        self.assertFalse(report["passed"])
        self.assertEqual(report["status"], "planned")

    def test_no_evidence_reuse_even_for_apparent_success(self):
        for evidence in ({}, {"passed": True, "baseline": self.base}, []):
            with self.assertRaisesRegex(ContractError, "reuse is unsupported"):
                self.report(evidence=evidence)

    def test_exact_manifest_bytes_and_mutation_rejected(self):
        path = self.root / "tools/selection.json"
        data = json.dumps(self.config, indent=4).encode()
        path.write_bytes(data)
        self.commit()
        loaded = load_manifest(path)
        report = select(self.root, self.base, "HEAD", loaded)
        self.assertEqual(report["manifest_sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(report["manifest_hash_encoding"], "exact_file_bytes")
        self.assertNotEqual(report["manifest_sha256"], report["canonical_manifest_sha256"])
        loaded["suites"][0]["always"] = False
        with self.assertRaisesRegex(ContractError, "manifest was modified"):
            select(self.root, self.base, "HEAD", loaded)

    def test_explicitly_mapped_manifest_change_stays_tooling(self):
        path = self.root / "tools/selection.json"
        self.write("tools/selection.json", json.dumps(self.config))
        self.base = self.commit()
        self.write("tools/selection.json", json.dumps(self.config, indent=2))
        self.commit()
        report = select(self.root, self.base, "HEAD", load_manifest(path))
        self.assertEqual(set(report["selected_suite_ids"]), {"integrity", "tools"})
        self.assertFalse(report["conservative_reasons"])

    def test_external_or_stale_loaded_manifest_rejected(self):
        external = Path(self.temp.name) / "external.json"
        external.write_text(json.dumps(self.config), encoding="utf-8")
        with self.assertRaisesRegex(ContractError, "inside root"):
            select(self.root, self.base, "HEAD", load_manifest(external))
        path = self.root / "tools/selection.json"
        path.write_text(json.dumps(self.config), encoding="utf-8")
        self.commit()
        loaded = load_manifest(path)
        path.write_text(json.dumps(self.config, indent=2), encoding="utf-8")
        self.commit()
        with self.assertRaisesRegex(ContractError, "committed head manifest"):
            select(self.root, self.base, "HEAD", loaded)

    def test_cli_and_standalone_copy_only_plan(self):
        path = self.root / "tools/selection.json"
        path.write_text(json.dumps(self.config), encoding="utf-8")
        self.commit()
        import tools.impact.selector as selector
        standalone = Path(self.temp.name) / "selector.py"
        shutil.copyfile(selector.__file__, standalone)
        result = subprocess.run([sys.executable, str(standalone), "--root", str(self.root),
                                 "--base", self.base, "--head", "HEAD", "--manifest", str(path)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "planned")
        bad = subprocess.run([sys.executable, str(standalone), "--root", str(self.root),
                              "--base", "missing", "--head", "HEAD", "--manifest", str(path)],
                             capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)


class ManifestTests(unittest.TestCase):
    def invalid(self, mutate):
        value = manifest()
        mutate(value)
        with self.assertRaises(ContractError):
            validate_manifest(value)

    def test_schema_unknown_types_duplicates_and_references(self):
        mutations = [
            lambda m: m.update(schema_version=True),
            lambda m: m.update(unrecognized=True),
            lambda m: m.update(components=[]),
            lambda m: m.update(suites=[]),
            lambda m: m["components"].append(copy.deepcopy(m["components"][0])),
            lambda m: m["suites"].append(copy.deepcopy(m["suites"][0])),
            lambda m: m["components"][0].update(depends_on=["missing"]),
            lambda m: m["suites"][0].update(depends_on=["missing"]),
            lambda m: m["suites"][0].update(components=["missing"]),
            lambda m: m["suites"][0].update(always=1),
            lambda m: m["suites"][0].update(command=[]),
            lambda m: m["suites"][0].update(command="python3 x.py"),
            lambda m: m["components"][0].update(paths=["../outside"]),
            lambda m: m["components"][0].update(paths=["scripts/*.gd"]),
            lambda m: m["components"][0].update(paths=["/absolute"]),
            lambda m: m["components"][0].update(paths=["scripts/**", "scripts/**"]),
            lambda m: m["content_rules"].append(copy.deepcopy(m["content_rules"][0])),
            lambda m: m["content_rules"][0].update(components=["missing"]),
            lambda m: m["content_rules"][0].update(constants={"GAIN.*": {"min": 0, "max": 1}}),
            lambda m: m["content_rules"][0].update(constants={"GAIN": {"min": 2, "max": 1}}),
            lambda m: m["content_rules"][0].update(constants={"GAIN": {"min": False, "max": 1}}),
            lambda m: m["content_rules"][0].update(constants={"GAIN": {"min": 0, "max": float("inf")}}),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                self.invalid(mutate)

    def test_component_and_suite_cycles(self):
        self.invalid(lambda m: m["components"][0].update(depends_on=["gain"]))
        self.invalid(lambda m: m["suites"][1].update(depends_on=["gain"]))
        self.invalid(lambda m: m["components"][0].update(depends_on=["audio"]))

    def test_components_without_reachable_suites_rejected(self):
        self.invalid(lambda m: m.update(suites=[s for s in m["suites"] if s["id"] not in {"audio", "gain"}]))
        value = manifest()
        # Core has no direct suite, but its dependants save and story do.
        self.assertIs(validate_manifest(value), value)

    def test_duplicate_json_keys_and_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "manifest.json"
            for text in ('{"schema_version":1,"schema_version":1}',
                         '{"schema_version":NaN}', '{"schema_version":Infinity}', '{}'):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ContractError):
                    load_manifest(path)


if __name__ == "__main__":
    unittest.main()
