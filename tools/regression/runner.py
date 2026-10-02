"""Fail-closed subprocess/result checks, independent of any game runtime.

Manifests execute trusted local commands, not sandboxed untrusted content.
No third-party packages, Godot installation, or Foundation runtime are imported.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1
LANES = ("source", "native_pck", "browser", "host")
COVERAGE_CATEGORIES = ("actions", "transitions", "guard_outcomes", "endings", "invariants")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_PREFIX = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_DIAGNOSTIC = re.compile(
    r"^\s*(?:\[[^\]\r\n]+\]\s*)?"
    r"(?:SCRIPT ERROR\s*:|ERROR\s*:|Parse Error\s*:|"
    r"Error (?:while )?importing\b|Failed to import\b|Import (?:error|failed)\b|"
    r"Failed (?:loading|to load) (?:script|resource)\b)",
    re.IGNORECASE,
)


class ContractError(ValueError):
    """An invalid manifest or result must never become a passing run."""


def _object(value: Any, where: str) -> dict:
    if not isinstance(value, dict):
        raise ContractError(f"{where} must be an object")
    return value


def _keys(value: dict, allowed: set[str], required: set[str], where: str) -> None:
    missing, unknown = required - value.keys(), value.keys() - allowed
    if missing:
        raise ContractError(f"{where} missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ContractError(f"{where} unknown fields: {', '.join(sorted(unknown))}")


def _text(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ContractError(f"{where} must be a nonempty string without NUL")
    return value


def _strings(value: Any, where: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ContractError(f"{where} must be {'a nonempty' if nonempty else 'an'} array")
    for item in value:
        _text(item, where + " item")
    if len(set(value)) != len(value):
        raise ContractError(f"{where} must contain unique strings")
    return value


def _integer(value: Any, where: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ContractError(f"{where} must be an integer >= {minimum}")
    return value


def _version(value: Any, where: str) -> None:
    if type(value) is not int or value != SCHEMA_VERSION:
        raise ContractError(f"{where} must equal {SCHEMA_VERSION}")


def _coverage(value: Any, where: str) -> dict[str, list[str]]:
    value = _object(value, where)
    _keys(value, set(COVERAGE_CATEGORIES), set(), where)
    return {category: _strings(value.get(category, []), f"{where}.{category}")
            for category in COVERAGE_CATEGORIES}


def _expected_errors(value: Any) -> list[dict]:
    if not isinstance(value, (list, tuple)):
        raise ContractError("expected_errors must be an array")
    lines = set()
    for entry in value:
        entry = _object(entry, "expected_errors item")
        _keys(entry, {"line", "count"}, {"line", "count"}, "expected_errors item")
        line = _text(entry["line"], "expected_errors.line")
        if "\n" in line or "\r" in line or _ANSI.search(line) or not _DIAGNOSTIC.match(line):
            raise ContractError("expected_errors.line must be one exact, uncolored diagnostic line")
        if not re.search(r"\w", _DIAGNOSTIC.sub("", line)):
            raise ContractError("expected_errors.line must include a specific diagnostic message")
        count = _integer(entry["count"], "expected_errors.count", minimum=1)
        if count > 100:
            raise ContractError("expected_errors.count must be <= 100")
        if line in lines:
            raise ContractError("expected_errors contains duplicate lines")
        lines.add(line)
    return list(value)


def _command_config(command: Any, cwd: Any, timeout_seconds: Any) -> None:
    if not isinstance(command, (list, tuple)) or not command:
        raise ContractError("command must be a nonempty argv array (no shell)")
    for argument in command:
        if not isinstance(argument, str) or "\x00" in argument:
            raise ContractError("command argv must contain strings without NUL")
    _text(command[0], "command executable")
    if not isinstance(cwd, (str, os.PathLike)):
        raise ContractError("cwd must be a path")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise ContractError("timeout_seconds must be a finite positive number")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ContractError("timeout_seconds must be a finite positive number")


def validate_manifest(manifest: Any) -> dict:
    """Validate without executing. Return the original object, never rewrite it."""
    manifest = _object(manifest, "manifest")
    _keys(manifest, {"schema_version", "suites", "coverage_targets", "required_lanes"},
          {"schema_version", "suites"}, "manifest")
    _version(manifest["schema_version"], "manifest.schema_version")
    required_lanes = _strings(manifest.get("required_lanes", list(LANES)), "required_lanes", nonempty=True)
    if set(required_lanes) - set(LANES):
        raise ContractError("required_lanes contains an unknown lane")
    if "coverage_targets" in manifest:
        _coverage(manifest["coverage_targets"], "coverage_targets")
    if not isinstance(manifest["suites"], list) or not manifest["suites"]:
        raise ContractError("suites must be a nonempty array")
    ids = set()
    for suite in manifest["suites"]:
        _validate_suite(suite)
        if suite["id"] in ids:
            raise ContractError(f"duplicate suite id: {suite['id']}")
        ids.add(suite["id"])
    return manifest


def _validate_suite(suite: Any) -> dict:
    suite = _object(suite, "suite")
    _keys(suite, {"id", "lane", "status", "reason", "command", "cwd", "timeout_seconds",
                  "result_prefix", "expected_scenario_ids", "expected_errors"}, {"id", "lane"}, "suite")
    if not isinstance(suite["id"], str) or not _IDENTIFIER.fullmatch(suite["id"]):
        raise ContractError("suite.id must be a safe 1-128 character identifier")
    if suite["lane"] not in LANES:
        raise ContractError("suite.lane is unknown")
    status = suite.get("status", "ready")
    if status not in ("ready", "blocked", "not_run"):
        raise ContractError("suite.status must be ready, blocked, or not_run")
    if status != "ready":
        _text(suite.get("reason"), "disabled suite.reason")
    else:
        required = {"command", "cwd", "timeout_seconds", "result_prefix", "expected_scenario_ids"}
        if required - suite.keys():
            raise ContractError("ready suite missing fields: " + ", ".join(sorted(required - suite.keys())))
        if "reason" in suite:
            raise ContractError("ready suite cannot declare a skipped reason")
    # Validate retained configuration even on disabled entries; a typo is not a skip.
    if any(key in suite for key in ("command", "cwd", "timeout_seconds")):
        if not all(key in suite for key in ("command", "cwd", "timeout_seconds")):
            raise ContractError("command, cwd, and timeout_seconds must be declared together")
        _command_config(suite["command"], suite["cwd"], suite["timeout_seconds"])
    if "result_prefix" in suite:
        if not isinstance(suite["result_prefix"], str) or not _PREFIX.fullmatch(suite["result_prefix"]):
            raise ContractError("result_prefix must be an uppercase identifier")
    if "expected_scenario_ids" in suite:
        _strings(suite["expected_scenario_ids"], "expected_scenario_ids", nonempty=True)
    _expected_errors(suite.get("expected_errors", []))
    return suite


def _json_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ContractError(f"non-finite JSON constant: {value}")


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_json_object, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as error:
        raise ContractError(f"invalid JSON: {error}") from error


def load_manifest(path: str | Path) -> dict:
    return validate_manifest(_parse_json(Path(path).read_text(encoding="utf-8")))


def validate_result(result: Any, *, suite_id: str, expected_scenario_ids: Sequence[str]) -> dict:
    """Validate one canonical envelope. A valid envelope may still report failure.

    Callers must separately check passed is True and failures is empty. Unknown
    top-level fields are rejected; scenario order does not matter, duplicates do.
    """
    result = _object(result, "result")
    required = {"schema_version", "suite_id", "scenario_ids", "passed", "failures", "checks"}
    _keys(result, required | {"coverage", "details"}, required, "result")
    _version(result["schema_version"], "result.schema_version")
    if result["suite_id"] != suite_id:
        raise ContractError(f"result suite_id must equal {suite_id!r}")
    ids = _strings(result["scenario_ids"], "result.scenario_ids", nonempty=True)
    if set(ids) != set(expected_scenario_ids):
        missing = sorted(set(expected_scenario_ids) - set(ids))
        extra = sorted(set(ids) - set(expected_scenario_ids))
        raise ContractError(f"scenario set mismatch: missing={missing}, unexpected={extra}")
    if type(result["passed"]) is not bool:
        raise ContractError("result.passed must be a boolean")
    if not isinstance(result["failures"], list):
        raise ContractError("result.failures must be an array")
    _integer(result["checks"], "result.checks")
    if "coverage" in result:
        _coverage(result["coverage"], "result.coverage")
    if "details" in result:
        _object(result["details"], "result.details")
        try:
            json.dumps(result["details"], allow_nan=False)
        except (ValueError, TypeError, RecursionError) as error:
            raise ContractError("result.details must be a JSON-compatible object") from error
    return result


def _kill_process_group(process: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass


def _inspect_output(output: bytes, expected_errors: Sequence[dict]) -> tuple[list[str], list[str]]:
    failures = []
    decoded = output.decode("utf-8", errors="replace")
    if "\ufffd" in decoded:
        failures.append("output contains invalid UTF-8 or replacement characters")
    diagnostic_lines = [_ANSI.sub("", line) for line in decoded.splitlines()
                        if _DIAGNOSTIC.match(_ANSI.sub("", line))]
    counts = Counter(diagnostic_lines)
    allowed = {entry["line"]: entry["count"] for entry in expected_errors}
    for line, count in counts.items():
        if line not in allowed:
            failures.append(f"unexpected diagnostic ({count}): {line}")
    for line, count in allowed.items():
        if counts[line] != count:
            failures.append(f"expected diagnostic count mismatch: wanted {count}, got {counts[line]}: {line}")
    return diagnostic_lines, failures


def inspect_log(log_path: str | Path, expected_errors: Sequence[dict] = ()) -> list[str]:
    """Inspect a preserved import/export log; return failures, not execution proof.

    A missing/unreadable log is a failure. The caller still owns exit-code,
    timeout, artifact existence, and structured-result checks for that command.
    """
    expected_errors = _expected_errors(expected_errors)
    try:
        output = Path(log_path).read_bytes()
    except OSError as error:
        return [f"could not read log: {error}"]
    return _inspect_output(output, expected_errors)[1]


def run_command(command: Sequence[str], *, cwd: str | Path, timeout_seconds: float,
                log_path: str | Path, expected_errors: Sequence[dict] = (),
                env: Mapping[str, str] | None = None) -> dict:
    """Run one checked command phase; no structured-suite or coverage claim.

    stdout/stderr are merged and preserved in log_path. env, when supplied, is
    the complete environment (use {**os.environ, ...} to override selectively).
    Expected diagnostics are exact normalized lines and exact occurrence counts.
    POSIX timeouts kill the process group, including children holding the pipe.
    """
    _command_config(command, cwd, timeout_seconds)
    expected_errors = _expected_errors(expected_errors)
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()
    failures: list[str] = []
    output = b""
    returncode = None
    timed_out = False
    process = None
    try:
        process = subprocess.Popen(list(command), cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, start_new_session=(os.name == "posix"))
        try:
            output, _ = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as error:
            timed_out = True
            output = error.output or b""
            _kill_process_group(process)
            try:
                output, _ = process.communicate(timeout=2)
            except subprocess.TimeoutExpired as final_error:
                output = final_error.output or output
                failures.append("output pipe remained open after timeout cleanup")
                if process.stdout:
                    process.stdout.close()
                process.wait(timeout=2)
            failures.append(f"command timed out after {timeout_seconds:g}s")
            if os.name != "posix":
                failures.append("non-POSIX timeout cannot guarantee descendant cleanup")
        returncode = process.returncode
    except OSError as error:
        failures.append(f"could not execute command: {error}")
    except BaseException:
        if process is not None:
            _kill_process_group(process)
            process.wait(timeout=2)
        raise
    finally:
        if process is not None and process.stdout is not None:
            process.stdout.close()
        path.write_bytes(output)
    duration = time.monotonic() - started
    if returncode is not None and returncode != 0:
        failures.append(f"command exited with status {returncode}")
    diagnostic_lines, log_failures = _inspect_output(output, expected_errors)
    failures.extend(log_failures)
    return {"status": "failed" if failures else "passed", "passed": not failures,
            "command": list(command), "cwd": str(Path(cwd).resolve()), "started_at": started_at,
            "duration_seconds": round(duration, 6), "timeout_seconds": timeout_seconds,
            "timed_out": timed_out, "returncode": returncode, "log_path": str(path.resolve()),
            "diagnostics": diagnostic_lines, "failures": failures}


def run_suite(suite: dict, *, base_dir: str | Path, output_dir: str | Path) -> dict:
    """Execute one manifest suite. All command and protocol checks must pass."""
    suite = _validate_suite(suite)
    record = {"id": suite["id"], "lane": suite["lane"], "result": None}
    if suite.get("status", "ready") != "ready":
        return {**record, "status": suite["status"], "reason": suite["reason"],
                "passed": False, "failures": [], "duration_seconds": 0.0, "log_path": None}
    cwd = Path(base_dir) / suite["cwd"]
    phase = run_command(suite["command"], cwd=cwd, timeout_seconds=suite["timeout_seconds"],
                        log_path=Path(output_dir) / (suite["id"] + ".log"),
                        expected_errors=suite.get("expected_errors", []))
    record.update(phase)
    prefix = suite["result_prefix"]
    lines = Path(record["log_path"]).read_text(encoding="utf-8", errors="replace").splitlines()
    candidates = [line for line in lines if _ANSI.sub("", line).lstrip().startswith(prefix)]
    failures = record["failures"]
    if len(candidates) != 1:
        failures.append(f"expected exactly one {prefix} result line; found {len(candidates)}")
    elif not candidates[0].startswith(prefix + " "):
        failures.append(f"result line must begin with the exact prefix plus one space: {prefix}")
    else:
        try:
            payload = candidates[0][len(prefix) + 1:]
            if not payload.startswith("{"):
                raise ContractError("result JSON must begin immediately after the single prefix space")
            result = validate_result(_parse_json(payload), suite_id=suite["id"],
                                     expected_scenario_ids=suite["expected_scenario_ids"])
            record["result"] = result
            if result["passed"] is not True:
                failures.append("result reported passed=false")
            if result["failures"]:
                failures.append("result reported nonempty failures")
        except ContractError as error:
            failures.append(str(error))
    record["passed"] = not failures
    record["status"] = "passed" if record["passed"] else "failed"
    return record


def _lane_status(records: list[dict]) -> str:
    if not records:
        return "not_run"
    statuses = {record["status"] for record in records}
    if "failed" in statuses:
        return "failed"
    if statuses == {"passed"}:
        return "passed"
    if len(statuses) == 1:
        return next(iter(statuses))
    return "incomplete"


def _coverage_report(records: list[dict], targets: dict, declared: bool) -> dict:
    observed = {category: set() for category in COVERAGE_CATEGORIES}
    reported = {category: set() for category in COVERAGE_CATEGORIES}
    for record in records:
        if record["result"] is None:
            continue
        for category, ids in _coverage(record["result"].get("coverage", {}), "coverage").items():
            reported[category].update(ids)
            if record["status"] == "passed":
                observed[category].update(ids)
    coverage = {
        "declared": declared,
        "categories": {category: {
            "expected": sorted(targets[category]), "reported": sorted(reported[category]),
            "observed": sorted(observed[category]),
            "covered": sorted(set(targets[category]) & observed[category]),
            "uncovered": sorted(set(targets[category]) - observed[category]),
            "unknown": sorted(reported[category] - set(targets[category])) if declared else [],
        } for category in COVERAGE_CATEGORIES},
    }
    coverage["complete"] = (all(not row["uncovered"] and not row["unknown"]
                                for row in coverage["categories"].values()) if declared else None)
    return coverage


def _write_report_atomic(report: dict, output_dir: str | Path) -> None:
    """Readers see either complete JSON version; never a partially written file."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    descriptor, temporary = tempfile.mkstemp(prefix=".report-", suffix=".tmp", dir=output_dir)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output_dir / "report.json")
    finally:
        temporary.unlink(missing_ok=True)


def begin_report(output_dir: str | Path) -> dict:
    """Atomically invalidate older evidence before validation or command startup.

    An interrupted/invalid run leaves this non-passing sentinel. in_progress means
    no final result was recorded; it does not assert that a process is still live.
    Adapters may call this before their own bootstrap or manifest loading steps.
    """
    report = {"schema_version": SCHEMA_VERSION, "execution_state": "in_progress",
              "status": "incomplete", "passed": False, "complete": False,
              "started_at": datetime.now(timezone.utc).isoformat(), "duration_seconds": 0.0,
              "reason": "No completed report exists for this invocation", "suites": []}
    _write_report_atomic(report, output_dir)
    return report


def run_manifest(manifest: dict, *, base_dir: str | Path, output_dir: str | Path) -> dict:
    """Run trusted local suites in order, retain every result, write report.json.

    No dependency order is implied: every ready suite runs, even after failures.
    Build/import dependencies belong in a game-owned adapter using run_command.
    """
    started = time.monotonic()
    started_at = begin_report(output_dir)["started_at"]
    validate_manifest(manifest)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    declared = "coverage_targets" in manifest
    targets = _coverage(manifest.get("coverage_targets", {}), "coverage_targets")
    records = []
    for suite in manifest["suites"]:
        record = run_suite(suite, base_dir=base_dir, output_dir=output_dir)
        result = record["result"]
        if declared and result is not None:
            for category, ids in _coverage(result.get("coverage", {}), "coverage").items():
                unknown = sorted(set(ids) - set(targets[category]))
                if unknown:
                    record["failures"].append(f"unknown coverage IDs in {category}: {unknown}")
                    record["passed"] = False
                    record["status"] = "failed"
        records.append(record)
    coverage = _coverage_report(records, targets, declared)
    coverage_by_lane = {lane: _coverage_report([record for record in records if record["lane"] == lane],
                                              targets, declared) for lane in LANES}
    required_lanes = manifest.get("required_lanes", list(LANES))
    lanes = {lane: {"status": _lane_status([record for record in records if record["lane"] == lane]),
                    "required": lane in required_lanes,
                    "suite_ids": [record["id"] for record in records if record["lane"] == lane]}
             for lane in LANES}
    failed = any(record["status"] == "failed" for record in records)
    complete = (all(record["status"] == "passed" for record in records)
                and all(lanes[lane]["status"] == "passed" for lane in required_lanes)
                and coverage["complete"] is not False)
    status = "failed" if failed else "passed" if complete else "incomplete"
    report = {"schema_version": SCHEMA_VERSION, "execution_state": "completed",
              "status": status, "passed": status == "passed",
              "complete": complete, "started_at": started_at,
              "duration_seconds": round(time.monotonic() - started, 6),
              "required_lanes": list(required_lanes), "lanes": lanes, "suites": records,
              "coverage": coverage, "coverage_by_lane": coverage_by_lane}
    _write_report_atomic(report, output_dir)
    return report
