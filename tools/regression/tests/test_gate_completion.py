"""Exercise the real CLI through its final summary, persisted report, and exit.

The integrity probe below is a synthetic consumer-owned check, not a new runner
integrity API. Every fixture and failure injection stays in a temporary directory.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[3]
PREFIX = "NEUTRAL_RESULT"
INTEGRITY_SCENARIOS = ["changed_source", "added_hidden_source", "repinned_source"]
INTEGRITY_PROBE = textwrap.dedent("""\
    import hashlib
    import json
    from pathlib import Path

    candidate = Path("candidate")
    # The predecessor is outside the mutable candidate and its generated pins.
    predecessor = json.loads(Path("predecessor.json").read_text(encoding="utf-8"))
    original = (candidate / "source.txt").read_bytes()
    completed = []
    failures = []

    def inventory():
        return {path.relative_to(candidate).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in candidate.rglob("*") if path.is_file()}

    def check_rejected(scenario):
        if inventory() == predecessor:
            failures.append("accepted mutation: " + scenario)
        completed.append(scenario)
        print("CHECK_COMPLETED " + scenario, flush=True)

    assert inventory() == predecessor, "neutral predecessor must initially match"
    (candidate / "source.txt").write_bytes(b"changed neutral source\\n")
    check_rejected("changed_source")
    (candidate / "source.txt").write_bytes(original)
    (candidate / ".unreviewed").write_text("hidden addition\\n", encoding="utf-8")
    check_rejected("added_hidden_source")
    (candidate / ".unreviewed").unlink()
    (candidate / "source.txt").write_bytes(b"changed and repinned\\n")
    Path("generated-pins.json").write_text(json.dumps(inventory()), encoding="utf-8")
    assert json.loads(Path("generated-pins.json").read_text(encoding="utf-8")) == inventory()
    check_rejected("repinned_source")
    result = {"schema_version": 1, "suite_id": "integrity", "scenario_ids": completed,
              "passed": not failures, "failures": failures, "checks": len(completed),
              "details": {"completed_negative_checks": completed}}
    print("NEUTRAL_RESULT " + json.dumps(result), flush=True)
""")


def envelope(suite_id="neutral", **changes):
    result = {"schema_version": 1, "suite_id": suite_id,
              "scenario_ids": ["neutral_check"], "passed": True,
              "failures": [], "checks": 1}
    result.update(changes)
    return result


def emit(result=None):
    return "print(" + repr(PREFIX + " " + json.dumps(envelope() if result is None else result)) + ", flush=True)"


def suite(code=None, suite_id="neutral", **changes):
    result = {"id": suite_id, "lane": "source",
              "command": [sys.executable, "-c", emit(envelope(suite_id)) if code is None else code],
              "cwd": ".", "timeout_seconds": 5, "result_prefix": PREFIX,
              "expected_scenario_ids": ["neutral_check"]}
    result.update(changes)
    return result


class GateCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest_path = self.root / "manifest.json"
        self.output = self.root / "evidence"
        self.report_path = self.output / "report.json"

    def invoke(self, suites=None, *, flags=(), env=None):
        if suites is not None:
            self.manifest_path.write_text(json.dumps({
                "schema_version": 1, "required_lanes": ["source"], "suites": suites,
            }), encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-m", "tools.regression", "run", "--manifest", str(self.manifest_path),
             "--output", str(self.output), *flags],
            cwd=ROOT, env=env, capture_output=True, text=True, timeout=20,
        )

    def assert_completed(self, process, status, exit_code):
        self.assertEqual(exit_code, process.returncode, process.stdout + process.stderr)
        self.assertEqual("", process.stderr)
        # No earlier or extra passing summary may escape before final aggregation.
        self.assertEqual(1, len(process.stdout.splitlines()), process.stdout)
        summary = json.loads(process.stdout)
        report = json.loads(self.report_path.read_text(encoding="utf-8"))
        for result in (summary, report):
            self.assertEqual("completed", result["execution_state"])
            self.assertEqual(status, result["status"])
            self.assertIs(status == "passed", result["passed"])
            self.assertIs(status == "passed", result["complete"])
        self.assertEqual(str(self.report_path.resolve()), summary["report"])
        return report

    def assert_in_progress(self):
        report = json.loads(self.report_path.read_text(encoding="utf-8"))
        self.assertEqual("in_progress", report["execution_state"])
        self.assertEqual("incomplete", report["status"])
        self.assertIs(False, report["passed"])
        self.assertIs(False, report["complete"])
        self.assertEqual([], report["suites"])
        return report

    def integrity_suite(self):
        import hashlib

        candidate = self.root / "candidate"
        candidate.mkdir()
        original = b"reviewed neutral source\n"
        (candidate / "source.txt").write_bytes(original)
        (self.root / "predecessor.json").write_text(
            json.dumps({"source.txt": hashlib.sha256(original).hexdigest()}), encoding="utf-8",
        )
        return suite(INTEGRITY_PROBE, "integrity", expected_scenario_ids=INTEGRITY_SCENARIOS)

    def assert_integrity_completed(self, record):
        self.assertEqual("integrity", record["id"])
        self.assertEqual("passed", record["status"])
        result = record["result"]
        self.assertEqual(INTEGRITY_SCENARIOS, result["scenario_ids"])
        self.assertEqual(INTEGRITY_SCENARIOS, result["details"]["completed_negative_checks"])
        self.assertEqual(len(INTEGRITY_SCENARIOS), result["checks"])
        self.assertEqual([], result["failures"])
        lines = Path(record["log_path"]).read_text(encoding="utf-8").splitlines()
        self.assertEqual(["CHECK_COMPLETED " + name for name in INTEGRITY_SCENARIOS], lines[:-1])
        self.assertEqual(result, json.loads(lines[-1].removeprefix(PREFIX + " ")))

    def test_integrity_negatives_reach_final_envelope_and_passing_report(self):
        process = self.invoke([self.integrity_suite()], flags=("--require-all",))
        report = self.assert_completed(process, "passed", 0)
        self.assertEqual(1, len(report["suites"]))
        self.assert_integrity_completed(report["suites"][0])

    def test_earlier_failure_does_not_skip_integrity_suite_or_final_report(self):
        process = self.invoke([suite("raise SystemExit(7)"), self.integrity_suite()])
        report = self.assert_completed(process, "failed", 1)
        self.assertEqual(["failed", "passed"], [row["status"] for row in report["suites"]])
        self.assert_integrity_completed(report["suites"][1])

    def test_late_result_failure_preserves_completed_integrity_evidence(self):
        failing = envelope("late", passed=False, failures=["neutral final assertion failed"])
        process = self.invoke([self.integrity_suite(), suite(emit(failing), "late")])
        report = self.assert_completed(process, "failed", 1)
        self.assert_integrity_completed(report["suites"][0])
        self.assertEqual(failing, report["suites"][1]["result"])
        self.assertEqual("failed", report["suites"][1]["status"])

    def test_early_success_followed_by_crash_fails_final_gate(self):
        process = self.invoke([suite(emit() + "; raise RuntimeError('neutral late crash')")])
        report = self.assert_completed(process, "failed", 1)
        record = report["suites"][0]
        self.assertEqual(envelope(), record["result"])
        self.assertEqual(1, record["returncode"])
        self.assertIn("RuntimeError: neutral late crash", Path(record["log_path"]).read_text())

    def test_early_success_followed_by_stderr_engine_error_fails_final_gate(self):
        code = emit() + "; import sys; print('SCRIPT ERROR: neutral late failure', file=sys.stderr, flush=True)"
        process = self.invoke([suite(code)])
        record = self.assert_completed(process, "failed", 1)["suites"][0]
        self.assertEqual(0, record["returncode"])
        self.assertEqual(envelope(), record["result"])
        self.assertEqual(["SCRIPT ERROR: neutral late failure"], record["diagnostics"])
        self.assertTrue(any("unexpected diagnostic" in failure for failure in record["failures"]))

    def test_passed_true_with_nonempty_failures_fails_final_gate(self):
        result = envelope(failures=["neutral observed failure"])
        record = self.assert_completed(self.invoke([suite(emit(result))]), "failed", 1)["suites"][0]
        self.assertEqual(result, record["result"])
        self.assertIn("result reported nonempty failures", record["failures"])

    def test_malformed_and_duplicate_results_fail_final_gate(self):
        cases = {
            "malformed": "print('NEUTRAL_RESULT {broken')",
            "duplicate_lines": emit() + "; " + emit(),
            "duplicate_keys": "print(" + repr(PREFIX + " " + json.dumps(envelope())[:-1] + ', "passed": true}') + ")",
        }
        for name, code in cases.items():
            with self.subTest(case=name):
                record = self.assert_completed(self.invoke([suite(code)]), "failed", 1)["suites"][0]
                self.assertIsNone(record["result"])
                self.assertTrue(record["failures"])
                self.assertIn(PREFIX, Path(record["log_path"]).read_text())

    def test_allow_incomplete_never_erases_observed_failure(self):
        blocked = {"id": "optional", "lane": "browser", "status": "blocked",
                   "reason": "Neutral adapter deliberately unavailable"}
        # Establish the report-only exception, then add an observed failure.
        process = self.invoke([suite(), blocked], flags=("--allow-incomplete",))
        self.assert_completed(process, "incomplete", 0)
        process = self.invoke([suite(emit(envelope(passed=False))), blocked], flags=("--allow-incomplete",))
        report = self.assert_completed(process, "failed", 1)
        self.assertEqual(["failed", "blocked"], [row["status"] for row in report["suites"]])

    def test_rejected_manifest_invalidates_previous_passing_report(self):
        for contents in ("{}", "{broken", None):
            with self.subTest(contents=contents):
                self.assert_completed(self.invoke([suite()]), "passed", 0)
                if contents is None:
                    self.manifest_path.unlink()
                else:
                    self.manifest_path.write_text(contents, encoding="utf-8")
                process = self.invoke()
                self.assertEqual(2, process.returncode, process.stderr)
                self.assertEqual("", process.stdout)
                self.assertIn("regression:", process.stderr)
                self.assert_in_progress()

    def test_final_report_write_failure_cannot_publish_success_or_keep_old_pass(self):
        self.assert_completed(self.invoke([suite()]), "passed", 0)
        injection = self.root / "fault-injection"
        injection.mkdir()
        # Fault-inject only final replacement in the CLI process. This keeps the
        # real -m entrypoint, command execution, aggregation, and I/O error path.
        # Unlike chmod, it is deterministic when tests run as root or on Windows.
        (injection / "sitecustomize.py").write_text(textwrap.dedent("""\
            import json
            import os
            from pathlib import Path

            original_replace = os.replace
            def fail_final_replace(source, destination, *args, **kwargs):
                if Path(destination).name == "report.json":
                    candidate = json.loads(Path(source).read_text(encoding="utf-8"))
                    if candidate.get("execution_state") == "completed":
                        raise OSError("synthetic final report replacement failure")
                return original_replace(source, destination, *args, **kwargs)
            os.replace = fail_final_replace
        """), encoding="utf-8")
        env = dict(os.environ)
        env["PYTHONPATH"] = str(injection) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        process = self.invoke([self.integrity_suite()], env=env)
        self.assertEqual(2, process.returncode, process.stdout + process.stderr)
        self.assertEqual("", process.stdout)
        self.assertIn("synthetic final report replacement failure", process.stderr)
        self.assert_in_progress()
        lines = (self.output / "integrity.log").read_text(encoding="utf-8").splitlines()
        self.assertEqual(["CHECK_COMPLETED " + name for name in INTEGRITY_SCENARIOS], lines[:-1])
        self.assertTrue(json.loads(lines[-1].removeprefix(PREFIX + " "))["passed"])
        self.assertEqual([], list(self.output.glob(".report-*.tmp")))


if __name__ == "__main__":
    unittest.main()
