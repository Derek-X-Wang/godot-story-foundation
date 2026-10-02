"""Self-tests deliberately manufacture false-green output and process failures."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from tools.regression import (
    ContractError, begin_report, inspect_log, load_manifest, run_command, run_manifest, run_suite,
    validate_manifest, validate_result,
)
from tools.regression.cli import main


def envelope(**changes):
    value = {"schema_version": 1, "suite_id": "neutral", "scenario_ids": ["open_gate"],
             "passed": True, "failures": [], "checks": 1}
    value.update(changes)
    return value


def emit(value=None):
    return "print(" + repr("NEUTRAL_RESULT " + json.dumps(envelope() if value is None else value)) + ", flush=True)"


def suite(code=None, **changes):
    value = {"id": "neutral", "lane": "source", "command": [sys.executable, "-c", emit() if code is None else code],
             "cwd": ".", "timeout_seconds": 5, "result_prefix": "NEUTRAL_RESULT",
             "expected_scenario_ids": ["open_gate"]}
    value.update(changes)
    return value


def manifest(*suites, **changes):
    value = {"schema_version": 1, "required_lanes": ["source"], "suites": list(suites) or [suite()]}
    value.update(changes)
    return value


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def run_suite(self, value):
        return run_suite(value, base_dir=self.root, output_dir=self.root / "logs")

    def run_manifest(self, value):
        return run_manifest(value, base_dir=self.root, output_dir=self.root / "logs")

    def test_pass_preserves_log_command_timing_and_report(self):
        value = manifest()
        report = self.run_manifest(value)
        self.assertEqual("passed", report["status"])
        self.assertEqual("completed", report["execution_state"])
        self.assertTrue(report["passed"])
        record = report["suites"][0]
        self.assertEqual(value["suites"][0]["command"], record["command"])
        self.assertEqual(0, record["returncode"])
        self.assertGreater(record["duration_seconds"], 0)
        self.assertIn("NEUTRAL_RESULT {", Path(record["log_path"]).read_text())
        self.assertEqual(report, json.loads((self.root / "logs/report.json").read_text()))
        self.assertEqual("not_run", report["lanes"]["browser"]["status"])
        self.assertFalse(report["lanes"]["browser"]["required"])
        self.assertIsNone(report["coverage"]["complete"])

    def assert_in_progress(self):
        current = json.loads((self.root / "logs/report.json").read_text())
        self.assertEqual("in_progress", current["execution_state"])
        self.assertEqual("incomplete", current["status"])
        self.assertFalse(current["passed"])
        self.assertFalse(current["complete"])
        self.assertEqual([], current["suites"])
        return current

    def test_begin_report_atomically_invalidates_previous_pass(self):
        self.run_manifest(manifest())
        started = begin_report(self.root / "logs")
        self.assertEqual(started, self.assert_in_progress())

    def test_invalid_manifest_cannot_leave_previous_passing_report(self):
        self.run_manifest(manifest())
        with self.assertRaises(ContractError):
            self.run_manifest({})
        self.assert_in_progress()

    def test_cli_invalid_or_unreadable_manifest_invalidates_previous_pass(self):
        path = self.root / "invalid.json"
        for contents in ("{}", "{invalid", None):
            self.run_manifest(manifest())
            if contents is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(contents)
            with self.subTest(contents=contents), redirect_stderr(io.StringIO()):
                self.assertEqual(2, main(["run", "--manifest", str(path), "--output", str(self.root / "logs")]))
                self.assert_in_progress()

    def test_interrupted_command_cannot_leave_previous_passing_report(self):
        self.run_manifest(manifest())
        # Exercise real command startup/cleanup, injecting a keyboard interrupt
        # at communicate. The new subprocess is killed by run_command's cleanup.
        with mock.patch.object(subprocess.Popen, "communicate", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_manifest(manifest(suite("import time; time.sleep(30)")))
        self.assert_in_progress()

    def test_report_replacements_are_complete_json_in_same_directory(self):
        self.run_manifest(manifest())
        replace = os.replace
        observed = []

        def inspect_replace(source, destination):
            source, destination = Path(source), Path(destination)
            self.assertEqual(source.parent, destination.parent)
            candidate = json.loads(source.read_text())
            existing = json.loads(destination.read_text())
            observed.append((existing["execution_state"], candidate["execution_state"]))
            replace(source, destination)

        with mock.patch("tools.regression.runner.os.replace", side_effect=inspect_replace):
            self.run_manifest(manifest())
        self.assertEqual([("completed", "in_progress"), ("in_progress", "completed")], observed)
        self.assertEqual([], list((self.root / "logs").glob(".report-*.tmp")))

    def test_failed_final_report_replacement_preserves_nonpassing_sentinel(self):
        self.run_manifest(manifest())
        replace = os.replace

        def fail_final_replace(source, destination):
            candidate = json.loads(Path(source).read_text())
            if candidate["execution_state"] == "completed":
                raise OSError("synthetic final report storage failure")
            replace(source, destination)

        with mock.patch("tools.regression.runner.os.replace", side_effect=fail_final_replace):
            with self.assertRaises(OSError):
                self.run_manifest(manifest())
        self.assert_in_progress()
        self.assertEqual([], list((self.root / "logs").glob(".report-*.tmp")))

    def test_valid_json_does_not_override_nonzero_exit(self):
        record = self.run_suite(suite(emit() + "; raise SystemExit(7)"))
        self.assertEqual("failed", record["status"])
        self.assertEqual(7, record["returncode"])
        self.assertIsNotNone(record["result"])

    def test_missing_executable_is_failure_and_log_exists(self):
        record = self.run_suite(suite(command=[str(self.root / "does-not-exist")]))
        self.assertEqual("failed", record["status"])
        self.assertIsNone(record["returncode"])
        self.assertTrue(Path(record["log_path"]).is_file())

    def test_wrong_cwd_fails(self):
        self.assertEqual("failed", self.run_suite(suite(cwd="missing"))["status"])

    def test_missing_malformed_duplicate_and_ambiguous_results_fail(self):
        codes = [
            "print('all checks passed')", "print('NEUTRAL_RESULT {broken')",
            emit() + ";" + emit(),
            "print('prefix NEUTRAL_RESULT {}')",
            "print(' NEUTRAL_RESULT ' + " + repr(json.dumps(envelope())) + ")",
            "print('NEUTRAL_RESULT  ' + " + repr(json.dumps(envelope())) + ")",
            "print('NEUTRAL_RESULTx {}');" + emit(),
            "print('NEUTRAL_RESULT\\t{}')", "print('NEUTRAL_RESULT []')",
            "print('\\x1b[31mNEUTRAL_RESULT ' + " + repr(json.dumps(envelope())) + " + '\\x1b[0m')",
        ]
        for code in codes:
            with self.subTest(code=code):
                self.assertEqual("failed", self.run_suite(suite(code))["status"])

    def test_false_pass_nonempty_failures_and_wrong_ids_fail(self):
        changes = [
            {"passed": False}, {"passed": True, "failures": ["synthetic failure"]},
            {"scenario_ids": ["different"]}, {"scenario_ids": []},
            {"scenario_ids": ["open_gate", "extra"]},
            {"scenario_ids": ["open_gate", "open_gate"]}, {"suite_id": "another"},
        ]
        for change in changes:
            with self.subTest(change=change):
                self.assertEqual("failed", self.run_suite(suite(emit(envelope(**change))))["status"])

    def test_exact_scenario_set_allows_reordering(self):
        value = envelope(scenario_ids=["second", "open_gate"])
        self.assertEqual("passed", self.run_suite(suite(emit(value), expected_scenario_ids=["open_gate", "second"]))["status"])

    def test_result_requires_strict_types_and_required_fields(self):
        changes = [
            {"schema_version": True}, {"schema_version": 2}, {"passed": 1},
            {"failures": ""}, {"checks": True}, {"checks": -1}, {"checks": 1.0},
            {"scenario_ids": [1]}, {"coverage": []}, {"coverage": {"unknown": []}},
            {"coverage": {"actions": ["a", "a"]}}, {"coverage": {"actions": [False]}},
            {"extra": "unversioned"},
        ]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ContractError):
                validate_result(envelope(**change), suite_id="neutral", expected_scenario_ids=["open_gate"])
        for field in envelope():
            invalid = envelope()
            del invalid[field]
            with self.subTest(missing=field), self.assertRaises(ContractError):
                validate_result(invalid, suite_id="neutral", expected_scenario_ids=["open_gate"])
        validate_result(envelope(checks=0), suite_id="neutral", expected_scenario_ids=["open_gate"])

    def test_duplicate_json_keys_and_nonfinite_constants_fail(self):
        payloads = [json.dumps(envelope())[:-1] + ', "passed": true}',
                    json.dumps(envelope()).replace('"checks": 1', '"checks": NaN')]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertEqual("failed", self.run_suite(suite("print(" + repr("NEUTRAL_RESULT " + payload) + ")"))["status"])

    def test_errors_before_and_after_result_and_stderr_fail(self):
        errors = ["ERROR: synthetic fault", "SCRIPT ERROR: synthetic fault", "Parse Error: synthetic fault",
                  "Error importing neutral.png", "Failed to import neutral.png", "Import failed for neutral.png",
                  "Failed loading resource neutral.tres", "[worker] ERROR: synthetic fault",
                  "  SCRIPT ERROR: synthetic fault", "\x1b[31mERROR: synthetic fault\x1b[0m"]
        for error in errors:
            for before in (True, False):
                code = "import sys;print(" + repr(error) + ", file=sys.stderr, flush=True)"
                code = code + ";" + emit() if before else emit() + ";" + code
                with self.subTest(error=error, before=before):
                    self.assertEqual("failed", self.run_suite(suite(code))["status"])

    def test_exact_expected_error_occurrence_contract(self):
        expected = [{"line": "ERROR: deliberate neutral rejection", "count": 1}]
        diagnostic = "print('ERROR: deliberate neutral rejection');"
        self.assertEqual("passed", self.run_suite(suite(diagnostic + emit(), expected_errors=expected))["status"])
        for code in (emit(), diagnostic + diagnostic + emit(),
                     diagnostic + "print('ERROR: different fault');" + emit(),
                     "print(' ERROR: deliberate neutral rejection');" + emit()):
            with self.subTest(code=code):
                self.assertEqual("failed", self.run_suite(suite(code, expected_errors=expected))["status"])
        # The same explicit line is not allowed in a different suite.
        second = suite(diagnostic + emit(envelope(suite_id="second")))
        second["id"] = "second"
        report = self.run_manifest(manifest(suite(diagnostic + emit(), expected_errors=expected), second))
        self.assertEqual(["passed", "failed"], [record["status"] for record in report["suites"]])

    def test_allowance_cannot_override_exit_or_false_result(self):
        allowed = [{"line": "ERROR: deliberate neutral rejection", "count": 1}]
        for tail in ("; raise SystemExit(3)", ""):
            code = "print('ERROR: deliberate neutral rejection');" + emit(envelope(passed=False)) + tail
            self.assertEqual("failed", self.run_suite(suite(code, expected_errors=allowed))["status"])

    def test_expected_errors_must_be_exact_bounded_diagnostics(self):
        invalid = [[{"line": "ERROR:", "count": 1}], [{"line": ".*", "count": 1}],
                   [{"line": "ERROR: something\nERROR: else", "count": 1}],
                   [{"line": "ERROR: message", "count": 0}], [{"line": "ERROR: message", "count": True}],
                   [{"line": "ERROR: message", "count": 101}], [{"line": "ERROR: message", "count": 1, "regex": True}],
                   [{"line": "ERROR: message", "count": 1}] * 2]
        for expected in invalid:
            with self.subTest(expected=expected), self.assertRaises(ContractError):
                validate_manifest(manifest(suite(expected_errors=expected)))

    def test_command_phase_requires_no_fake_suite_result(self):
        phase = run_command([sys.executable, "-c", "print('neutral import complete')"], cwd=self.root,
                            timeout_seconds=5, log_path=self.root / "import.log")
        self.assertTrue(phase["passed"])
        self.assertNotIn("result", phase)
        phase = run_command([sys.executable, "-c", "print('ERROR: import failed')"], cwd=self.root,
                            timeout_seconds=5, log_path=self.root / "import.log")
        self.assertFalse(phase["passed"])

    def test_preserved_logs_are_inspected_without_claiming_execution(self):
        path = self.root / "nested-import.log"
        self.assertTrue(inspect_log(path))
        path.write_text("normal import\n")
        self.assertEqual([], inspect_log(path))
        path.write_text("ERROR: deliberate neutral rejection\n")
        self.assertTrue(inspect_log(path))
        self.assertEqual([], inspect_log(path, [{"line": "ERROR: deliberate neutral rejection", "count": 1}]))
        self.assertTrue(inspect_log(path, [{"line": "ERROR: deliberate neutral rejection", "count": 2}]))

    def test_details_is_explicit_extensible_json_object(self):
        value = envelope(details={"seed": 17, "legacy_result": {"passes": 4}, "limits": ["neutral fixture"]})
        self.assertEqual("passed", self.run_suite(suite(emit(value)))["status"])
        for details in ([], None, "value", {"nonfinite": float("inf")}):
            with self.subTest(details=details), self.assertRaises(ContractError):
                validate_result(envelope(details=details), suite_id="neutral", expected_scenario_ids=["open_gate"])

    def test_invalid_utf8_cannot_hide_diagnostic(self):
        code = "import sys;sys.stdout.buffer.write(b'\\xff\\n');" + emit()
        self.assertEqual("failed", self.run_suite(suite(code))["status"])

    def test_timeout_preserves_early_log_and_rejects_early_pass(self):
        record = self.run_suite(suite(emit() + "; import time; time.sleep(30)", timeout_seconds=0.1))
        self.assertTrue(record["timed_out"])
        self.assertEqual("failed", record["status"])
        self.assertIn("NEUTRAL_RESULT", Path(record["log_path"]).read_text())
        self.assertLess(record["duration_seconds"], 5)

    @unittest.skipUnless(os.name == "posix", "process-group guarantee is POSIX-only")
    def test_timeout_kills_descendant_even_when_leader_exits(self):
        marker = self.root / "survived"
        child_code = "import time,pathlib; time.sleep(0.6); pathlib.Path(" + repr(str(marker)) + ").write_text('survived')"
        for leader_exits in (False, True):
            code = ("import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(child_code) + "]);"
                    + emit() + ("" if leader_exits else ";time.sleep(30)"))
            record = self.run_suite(suite(code, timeout_seconds=0.15))
            self.assertTrue(record["timed_out"])
            self.assertEqual("failed", record["status"])
            time.sleep(0.7)
            self.assertFalse(marker.exists(), "descendant escaped timeout cleanup")

    def test_blocked_and_not_run_do_not_execute(self):
        marker = self.root / "must-not-exist"
        code = "from pathlib import Path; Path(" + repr(str(marker)) + ").touch()"
        for status in ("blocked", "not_run"):
            value = suite(code, status=status, reason="Synthetic unavailable prerequisite")
            record = self.run_suite(value)
            self.assertEqual(status, record["status"])
            self.assertFalse(record["passed"])
            self.assertIsNone(record["result"])
            self.assertIsNone(record["log_path"])
            self.assertFalse(marker.exists())
        report = self.run_manifest(manifest({"id": "later", "lane": "browser", "status": "not_run", "reason": "Not selected"}))
        self.assertEqual("incomplete", report["status"])
        self.assertFalse(report["passed"])

    def test_default_scope_never_hides_missing_lanes(self):
        value = manifest()
        del value["required_lanes"]
        report = self.run_manifest(value)
        self.assertEqual("incomplete", report["status"])
        self.assertFalse(report["passed"])
        self.assertEqual("not_run", report["lanes"]["native_pck"]["status"])
        self.assertTrue(report["lanes"]["native_pck"]["required"])

    def test_failure_does_not_prevent_other_suites_reporting(self):
        report = self.run_manifest(manifest(suite("raise SystemExit(2)"),
                                  suite(emit(envelope(suite_id="second")), id="second")))
        self.assertEqual(["failed", "passed"], [record["status"] for record in report["suites"]])

    def test_actual_coverage_and_uncovered_not_check_counts(self):
        result = envelope(checks=10000, coverage={"actions": ["inspect"], "guard_outcomes": ["closed"]})
        targets = {"actions": ["inspect", "open"], "guard_outcomes": ["closed", "open"]}
        report = self.run_manifest(manifest(suite(emit(result)), coverage_targets=targets))
        self.assertEqual("incomplete", report["status"])
        self.assertFalse(report["passed"])
        category = report["coverage"]["categories"]["actions"]
        self.assertEqual(["inspect"], category["covered"])
        self.assertEqual(["open"], category["uncovered"])
        self.assertEqual([], category["unknown"])

    def test_complete_coverage_passes_and_union_spans_suites(self):
        targets = {"actions": ["inspect", "open"]}
        first = suite(emit(envelope(coverage={"actions": ["inspect"]})))
        second = suite(emit(envelope(suite_id="second", coverage={"actions": ["open"]})), id="second")
        report = self.run_manifest(manifest(first, second, coverage_targets=targets))
        self.assertEqual("passed", report["status"])
        self.assertTrue(report["coverage"]["complete"])

    def test_source_coverage_never_implies_browser_coverage(self):
        targets = {"actions": ["inspect"]}
        report = self.run_manifest(manifest(suite(emit(envelope(coverage=targets))), coverage_targets=targets))
        self.assertTrue(report["coverage"]["complete"])
        self.assertTrue(report["coverage_by_lane"]["source"]["complete"])
        self.assertFalse(report["coverage_by_lane"]["browser"]["complete"])
        self.assertEqual(["inspect"], report["coverage_by_lane"]["browser"]["categories"]["actions"]["uncovered"])
        self.assertEqual([], report["coverage_by_lane"]["browser"]["categories"]["actions"]["observed"])

    def test_unknown_coverage_fails_and_failed_observations_do_not_count(self):
        result = envelope(coverage={"actions": ["inspect", "invented"]})
        report = self.run_manifest(manifest(suite(emit(result)), coverage_targets={"actions": ["inspect"]}))
        self.assertEqual("failed", report["status"])
        category = report["coverage"]["categories"]["actions"]
        self.assertEqual(["invented"], category["unknown"])
        self.assertEqual(["inspect"], category["uncovered"])
        self.assertEqual([], category["observed"])
        self.assertEqual(["inspect", "invented"], category["reported"])

    def test_coverage_not_declared_makes_no_completeness_claim(self):
        report = self.run_manifest(manifest(suite(emit(envelope(coverage={"actions": ["inspect"]})))))
        self.assertFalse(report["coverage"]["declared"])
        self.assertIsNone(report["coverage"]["complete"])
        self.assertEqual(["inspect"], report["coverage"]["categories"]["actions"]["observed"])

    def test_missing_coverage_does_not_infer_from_scenario_or_checks(self):
        report = self.run_manifest(manifest(coverage_targets={"actions": ["open_gate"]}))
        self.assertEqual("incomplete", report["status"])
        self.assertEqual(["open_gate"], report["coverage"]["categories"]["actions"]["uncovered"])

    def test_manifest_rejects_mistyped_or_unsafe_configuration(self):
        bad_suites = [{"id": "../escape"}, {"id": ""}, {"lane": "invented"}, {"status": "passed"},
                      {"status": "blocked"}, {"reason": "skip ready"}, {"command": "echo pass"},
                      {"command": []}, {"command": [False]}, {"timeout_seconds": 0},
                      {"timeout_seconds": True}, {"timeout_seconds": float("inf")},
                      {"timeout_seconds": float("nan")}, {"result_prefix": "lowercase"},
                      {"result_prefix": "RESULT "}, {"expected_scenario_ids": []},
                      {"expected_scenario_ids": ["a", "a"]}, {"cwd": 4}, {"typo": "value"}]
        for change in bad_suites:
            with self.subTest(change=change), self.assertRaises(ContractError):
                validate_manifest(manifest(suite(**change)))
        bad_manifests = [{"schema_version": True}, {"schema_version": 2}, {"suites": []},
                         {"required_lanes": []}, {"required_lanes": ["not-real"]},
                         {"required_lanes": ["source", "source"]}, {"coverage_targets": {"unknown": []}},
                         {"coverage_targets": {"actions": ["a", "a"]}}, {"typo": True}]
        for change in bad_manifests:
            with self.subTest(change=change), self.assertRaises(ContractError):
                validate_manifest(manifest(**change))
        with self.assertRaises(ContractError):
            validate_manifest(manifest(suite(), suite()))

    def test_manifest_loader_rejects_duplicate_keys(self):
        path = self.root / "manifest.json"
        path.write_text('{"schema_version":1,"schema_version":1,"suites":[]}')
        with self.assertRaises(ContractError):
            load_manifest(path)

    def test_cli_exit_policy_failed_incomplete_invalid_and_pass(self):
        path = self.root / "manifest.json"
        arguments = ["run", "--manifest", str(path), "--output", str(self.root / "logs")]
        cases = [(manifest(), 0, 0, 0), (manifest(suite("raise SystemExit(1)")), 1, 1, 1),
                 (manifest(coverage_targets={"actions": ["uncovered"]}), 3, 3, 0),
                 (manifest({"id": "blocked", "lane": "source", "status": "blocked", "reason": "Unavailable"}), 3, 3, 0),
                 (manifest({"id": "deferred", "lane": "source", "status": "not_run", "reason": "Not selected"}), 3, 3, 0)]
        missing_lanes = manifest()
        del missing_lanes["required_lanes"]
        cases.append((missing_lanes, 3, 3, 0))
        for value, default_code, strict_code, permissive_code in cases:
            path.write_text(json.dumps(value))
            with self.subTest(value=value), redirect_stdout(io.StringIO()):
                self.assertEqual(default_code, main(arguments))
                self.assertEqual(strict_code, main(arguments + ["--require-all"]))
                self.assertEqual(permissive_code, main(arguments + ["--allow-incomplete"]))
                report = json.loads((self.root / "logs/report.json").read_text())
                self.assertEqual(default_code == 0, report["passed"])
                self.assertEqual(default_code == 0, report["complete"])
        path.write_text("{}")
        with redirect_stderr(io.StringIO()):
            self.assertEqual(2, main(arguments))
        path.write_text(json.dumps(manifest()))
        with redirect_stdout(io.StringIO()):
            self.assertEqual(0, main(["validate", "--manifest", str(path)]))

    def test_cli_policy_flags_are_mutually_exclusive(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            main(["run", "--manifest", "unused.json", "--output", str(self.root),
                  "--require-all", "--allow-incomplete"])
        self.assertEqual(2, caught.exception.code)

    def test_cli_module_entry_and_relative_cwd(self):
        path = self.root / "manifest.json"
        value = manifest(suite("from pathlib import Path; assert Path('neutral.txt').read_text() == 'fixture';" + emit()))
        (self.root / "neutral.txt").write_text("fixture")
        path.write_text(json.dumps(value))
        root = Path(__file__).resolve().parents[3]
        process = subprocess.run([sys.executable, "-m", "tools.regression", "run", "--manifest", str(path),
                                  "--output", str(self.root / "logs"), "--require-all"], cwd=root, capture_output=True, text=True)
        self.assertEqual(0, process.returncode, process.stderr)
        self.assertEqual("passed", json.loads(process.stdout)["status"])

    def test_toolkit_runs_after_standalone_copy_and_rename(self):
        original = Path(__file__).resolve().parents[1]
        standalone = self.root / "foundation_regression"
        shutil.copytree(original, standalone, ignore=shutil.ignore_patterns("__pycache__", "tests"))
        environment = {**os.environ, "PYTHONPATH": str(self.root)}
        process = subprocess.run([sys.executable, "-m", "foundation_regression", "run", "--manifest",
                                  str(standalone / "examples/manifest.json"), "--output", str(self.root / "evidence")],
                                 cwd=self.root, env=environment, capture_output=True, text=True)
        self.assertEqual(0, process.returncode, process.stderr)
        self.assertEqual("passed", json.loads(process.stdout)["status"])


if __name__ == "__main__":
    unittest.main()
