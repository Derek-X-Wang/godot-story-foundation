# Optional regression runner (contract v1)

This standard-library-only Python toolkit checks **trusted local commands** and
their explicit regression results. It can be copied independently; it imports no
Foundation narrative, scene, authoring, art, Godot, or browser modules. Python
3.10+ is required. The included example and self-tests are original, neutral
synthetic fixtures under the repository MIT license.

The toolkit owns process/result validation and evidence reporting. A consuming
game owns scenarios, identifiers, coverage targets, commands, saves, build/import
steps, browser automation, and the truth of its observations. A command manifest
is executable configuration, **not an untrusted-content sandbox**. The runner
does not download engines, install dependencies, publish artifacts, or execute a
browser on behalf of a lane label.

## Run and test

From the repository root:

```sh
python3 -m unittest discover -s tools/regression/tests -v
python3 -m tools.regression validate --manifest tools/regression/examples/manifest.json
python3 -m tools.regression run --manifest tools/regression/examples/manifest.json \
  --output .build/regression-example
```

The neutral example explicitly selects only `source` as its required scope.
Its report still lists `native_pck`, `browser`, and `host` as `not_run`. This is a
runner/protocol demonstration; it proves no Godot or platform compatibility.
Use a new output directory for each evidence run: an explicit reused directory
replaces its suite logs and `report.json`. Logs can contain game-private content;
keep consuming-game reports in that game's private storage.

Every run first atomically replaces `report.json` with a non-passing sentinel:
`execution_state: in_progress`, `status: incomplete`, `passed: false`, and
`complete: false`. This happens before manifest validation or command startup;
the CLI also does it before opening/parsing the manifest. Successful aggregation
atomically replaces that sentinel with the final report and
`execution_state: completed`, including for failed or incomplete results.
Thus an invalid manifest, interruption, or failed final write cannot leave an
older passing report as current evidence. An `in_progress` report means no final
result was recorded; it does **not** guarantee a process is still running. Do not
interpret older suite logs on their own as current results. Each output directory
must have one writer; concurrent invocations need separate directories. If the
initial sentinel cannot be written, execution stops with an I/O error; no program
can invalidate an older file on storage it cannot write.

CLI exit codes:

- `0`: the required scope and declared combined coverage passed completely
- `1`: one or more observed execution, protocol, or unknown-coverage failures
- `2`: invalid manifest, unreadable input, or runner I/O error
- `3`: incomplete scope/coverage, including blocked or unexecuted suites/lanes

Strict, fail-closed exit policy is the default. `--require-all` remains an accepted
explicit spelling of that policy. For report-only use, `--allow-incomplete` opts
into exit zero for incomplete runs; the report and printed summary still say
`status: incomplete`, `passed: false`, and `complete: false`. These flags are
mutually exclusive. Never use `--allow-incomplete` for a release or CI gate.
Observed failures always exit one, including with `--allow-incomplete`. There is
no “all pass” label for incomplete runs. A command-phase check is not a
scenario-suite pass.

## Manifest contract

```json
{
  "schema_version": 1,
  "required_lanes": ["source", "native_pck", "browser", "host"],
  "coverage_targets": {
    "actions": ["inspect_gate", "open_gate"],
    "transitions": ["closed_to_open"],
    "guard_outcomes": ["open.allowed", "open.blocked"],
    "endings": ["gate_open"],
    "invariants": ["closed_gate_unchanged", "opened_once"]
  },
  "suites": [
    {
      "id": "neutral_source",
      "lane": "source",
      "command": ["python3", "neutral_suite.py"],
      "cwd": ".",
      "timeout_seconds": 10,
      "result_prefix": "NEUTRAL_RESULT",
      "expected_scenario_ids": ["closed_gate", "open_gate"]
    },
    {
      "id": "browser_probe",
      "lane": "browser",
      "status": "blocked",
      "reason": "Browser adapter has not been supplied"
    },
    {
      "id": "native_probe",
      "lane": "native_pck",
      "status": "not_run",
      "reason": "This run did not select native export verification"
    }
  ]
}
```

- `schema_version` is integer `1`; unknown fields and duplicate JSON keys fail
- `suites` is a nonempty list with unique safe `id` values (1–128 letters,
  digits, dots, underscores, or hyphens; starts with a letter/digit)
- `lane` is exactly `source`, `native_pck`, `browser`, or `host`
- `required_lanes` defaults to **all four lanes**. Omitted lanes are `not_run`.
  An explicit nonempty subset narrows the claimed scope and remains in the report
- Runnable suites have `status` omitted or `ready`, nonempty argv `command`,
  `cwd`, finite positive `timeout_seconds`, uppercase identifier `result_prefix`,
  and nonempty unique `expected_scenario_ids`
- Commands execute without a shell. No environment interpolation, glob expansion,
  command substitution, or implicit prerequisite/dependency ordering occurs
- Relative `cwd` resolves against the manifest's directory in the CLI (against
  `base_dir` in the Python API). Absolute paths are allowed. Relative executable
  paths follow subprocess rules from that working directory
- `blocked` means a stated prerequisite prevents execution; `not_run` means
  deliberately unexecuted scope. Both require a nonempty `reason`, never execute
  even if command fields are retained, and never earn a passing result
- Retained command configuration on disabled entries is still validated
- Every ready suite runs even after another fails, preserving independent evidence

## Strict one-line result

A suite must print exactly one raw line in the combined stdout/stderr stream:

```text
NEUTRAL_RESULT {"schema_version":1,"suite_id":"neutral_source","scenario_ids":["closed_gate","open_gate"],"passed":true,"failures":[],"checks":6,"coverage":{"actions":["inspect_gate","open_gate"],"transitions":["closed_to_open"],"guard_outcomes":["open.allowed","open.blocked"],"endings":["gate_open"],"invariants":["closed_gate_unchanged","opened_once"]}}
```

The prefix is immediately followed by one space and the JSON object. Leading
whitespace, colored prefixes, malformed/duplicate prefix lines, missing lines,
duplicate JSON keys, non-finite numbers, unknown top-level fields, and wrong
schema versions fail. Other ordinary output is retained. Result scenario IDs
must match the declared set **exactly**; order is irrelevant, duplicates fail.

Required envelope fields:

- `schema_version`: integer `1`
- `suite_id`: the exact suite ID
- `scenario_ids`: nonempty unique strings, the actual completed scenario set
- `passed`: boolean, must be `true` to pass
- `failures`: array, must be empty to pass
- `checks`: nonnegative integer, not a boolean; descriptive assertion count only

Optional fields:

- `coverage`: object of unique-string arrays under the five categories above
- `details`: JSON object for game-owned diagnostic evidence, e.g. seed, replay
  failure index, legacy results, entry path, limitations, or phase timings

Passing also requires exit status zero, no timeout, and no unexpected diagnostic
anywhere in the **complete** log, including after a valid success result. A
zero exit with an engine error is a failure. A valid early success result followed
by a hang/nonzero exit is a failure. `validate_result` only validates the envelope;
its caller must separately enforce `passed is True` and an empty failure list.

## Engine diagnostics and bounded exceptions

The scanner strips ANSI color sequences and detects line-start `ERROR:`,
`SCRIPT ERROR:`, `Parse Error:`, common explicit import-failure lines, and
script/resource load failures (case-insensitive, with optional leading whitespace
or one bracketed log label). It scans merged stdout/stderr, including final lines.
This is not a universal parser for every tool's diagnostic format: an adapter
must additionally validate its tool-specific failure signals and artifacts.

Negative tests may require an exact expected diagnostic:

```json
"expected_errors": [
  {"line": "ERROR: deliberate neutral rejection", "count": 1}
]
```

Each exception belongs only to that suite/command, names a whole uncolored line
including whitespace, and requires its exact occurrence count (1–100). Missing,
extra, or changed lines fail. Regexes, substring allowances, blank messages,
multiline patterns, duplicate allowances, and global ignore rules are rejected.
An allowance never overrides a bad exit, timeout, or failed result. It cannot
silence unrelated parser/import errors. These are observed diagnostic exceptions,
not arbitrary permission to ignore errors.

## Coverage evidence, not assertion arithmetic

`coverage_targets` is optional. Without it, coverage completeness is `null` and
the report makes no completeness claim. When declared, omitted categories mean
empty target sets. Every reported ID must be in the declared category's target
set; an unknown ID fails its suite. Duplicate and unknown category names fail.

For every category the report retains:

- `expected`: declared target IDs
- `reported`: IDs in structurally valid results, even from failed suites
- `observed`: IDs from suites that passed **all** process/protocol/coverage checks
- `covered`: expected IDs intersecting observed IDs
- `uncovered`: expected IDs without accepted evidence
- `unknown`: reported IDs absent from declared targets (only when targets exist)

Missing IDs make the run incomplete. Failed-suite observations do not count as
covered. Checks and scenario counts never invent action, transition, guard,
ending, or invariant coverage. A game adapter must add IDs when those behaviors
actually execute and validate its mapping; the runner cannot authenticate a
fixture's claim or discover omitted game mechanics.

`coverage` is explicitly the **combined union**. `coverage_by_lane` reports the
same categories independently for every lane against the same target universe.
Source evidence never populates browser/native evidence. Combined completeness
does not promise target completeness in each lane; inspect `coverage_by_lane`
for that question, or run separate manifests with lane-specific targets. A host
check that does not execute gameplay naturally has no gameplay coverage.

Top-level `passed` means every configured suite passed, all declared required
lanes contain only passing suites, and combined declared targets are covered.
It is always scoped by `required_lanes`; it does not grant a broader platform or
browser compatibility claim. Any blocked/not-run configured suite prevents a
complete result, even if its lane is outside the narrowed required scope.

## Adapter APIs and import/export phases

```python
from pathlib import Path
from tools.regression import inspect_log, run_command, run_manifest

phase = run_command(
    ["godot", "--headless", "--path", str(project), "--editor", "--quit"],
    cwd=project,
    timeout_seconds=90,
    log_path=Path(output) / "import.log",
)
if phase["status"] != "passed":
    raise RuntimeError(phase["failures"])
# Also verify expected generated artifacts; a clean exit alone does not prove them.

report = run_manifest(manifest, base_dir=manifest_directory, output_dir=output)
```

`run_command(command, *, cwd, timeout_seconds, log_path, expected_errors=(),
env=None)` returns a dict with `status`, `passed`, `failures`, argv/cwd, UTC start,
elapsed seconds, timeout flag, return code, absolute log path, and diagnostics.
It has **no suite-result or coverage claim**, suitable for normal import/export
commands that do not print a suite envelope. If `env` is supplied it is the
complete environment; use `{**os.environ, "KEY": "value"}` for overrides.

`inspect_log(log_path, expected_errors=()) -> list[str]` checks a preserved nested
log and returns failure descriptions. Missing/unreadable logs fail. It does not
prove the originating command exited successfully, completed on time, generated
expected artifacts, or emitted a valid suite result. A game-owned build adapter
must check all those facts and inspect any logs hidden by redirection.

`run_suite(suite, *, base_dir, output_dir) -> dict` checks one suite; full-manifest
coverage-target membership checks are added by `run_manifest`.
`begin_report(output_dir) -> dict` atomically writes the non-passing start sentinel;
adapters can call it before their own bootstrap, hash checks, or manifest loading.
`run_manifest` calls it before validating the supplied manifest. `run_suite` and
`run_command` do not manage an aggregate report or claim aggregate completion.
`load_manifest(path)` and `validate_manifest(value)` validate without execution
or report writes; the CLI `validate` subcommand is likewise read-only.
`validate_result(value, *, suite_id, expected_scenario_ids)` validates an envelope.
`ContractError` signals malformed configuration or result data.

Timeouts use a new POSIX process session and kill its process group, including
ordinary descendants and descendants holding output open after the leader exits.
Raw combined bytes are preserved. Non-POSIX systems kill the direct child and
explicitly report that descendant cleanup is not guaranteed after a timeout.
Deliberately detached processes are outside the cleanup guarantee; manifests
must contain trusted commands. The runner buffers command output in memory, so
keep logs bounded in game adapters. No background process or monitor is created.

## Verification limits

Self-tests exercise zero/nonzero exits, missing executables and bad working
directories, malformed/missing/duplicate/false results, exact scenario matching,
strict JSON/types, stderr/late engine errors, exact-count expected diagnostics,
timeouts with child processes, blocked/not-run entries, unknown/uncovered IDs,
per-lane evidence, clean command phases, nested logs, CLI policy, and standalone
use, plus stale-report invalidation on rejected/interrupted runs and atomic
report replacement. These are runner correctness checks; they are not real-engine, browser,
native PCK, game-mechanic, or proprietary-game coverage.
