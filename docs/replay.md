# Optional semantic replay records (schema 1)

`addons/story_foundation/testing/replay_record.gd` is an independently usable,
MIT-licensed GDScript helper for small deterministic regression traces. Copy the
script and its `.uid` into any Godot 4.6.3 project and preload the copied path.
There is no addon installation, autoload, narrative runtime, Dialogue Manager,
scene, save-system or offline-authoring dependency. The helper does not dispatch
game commands, infer game state, explore actions or shrink failures.

The game-owned adapter supplies semantic snapshots, action payloads, stable action
IDs, reset/action execution and expectations. It owns all mutable state and actual
game operations. A replay applies recorded actions through that adapter, then
compares the resulting state; applying recorded deltas to the game is **not** a
replay. Deltas are only validation and diagnostic data. Coverage is exactly the
state and invariants selected by the adapter. Omitted UI, RNG, timers, saves,
custom mechanics and external side effects are not automatically covered.

## Implemented example and check

From the repository root, with Python 3.11+ and Godot 4.6.3:

```sh
python3 scripts/test_replay.py --godot /path/to/godot
```

This assembles a temporary project containing only the helper,
[`seeded_replay.gd`](../examples/replay/seeded_replay.gd),
[`test_replay.gd`](../tests/regression/test_replay.gd) and a minimal project file.
It runs unit checks, captures the same seeded action sequence twice and compares
record bytes, replays it in a fresh process, removes the original project, and
replays again in a fresh relocated project without an import cache. A changed
build identity must fail before adapter reset/actions. No other Foundation module
or downloaded dependency is copied into the project.

The intentionally faulty, original synthetic example transfers 1–4 units from a
stock of 100 to a collected balance. A game-owned `RandomNumberGenerator` with
seed 73491 selects each transfer amount. On turn 7 the adapter deliberately adds
the amount twice. Capture stops at its first failed conservation expectation,
zero-based step 6, and replay reproduces both the exact faulty state and the same
expectation failure. This demonstrates a small seeded trace, not general gameplay
exploration, optimal coverage or automatic minimization.

To run the example manually, copy the helper as `replay_record.gd` and the example
as `seeded_replay.gd` into an otherwise empty Godot project, then run:

```sh
godot --headless --path /path/to/project --script res://seeded_replay.gd -- --capture /tmp/trace.json
godot --headless --path /path/to/project --script res://seeded_replay.gd -- --replay /tmp/trace.json
```

The demo exits 0 when the **deliberately injected** failure is captured/reproduced
as designed. Production CI must choose its own failure policy: exact replay
success is distinct from an expectation passing.

## Small public API

All methods are static. Every fallible operation returns a Dictionary with `ok`.
Failures include `error` and `step_index` (`-1` outside a step). Capture and query
arguments are never mutated except the explicit successful `append_step` change.

- `canonical(value) -> {ok, json, hash}` validates the domain below, produces
  canonical JSON and its lowercase SHA-256 over UTF-8 bytes
- `begin(identity, seed, initial_state) -> {ok, record}` creates a deep-copied record
- `append_step(record, action_id, action, before_state, after_state, expectation={})`
  appends atomically and returns `{ok, step_index}`. The before state must continue
  the recorded state. IDs must be nonempty; the same stable gameplay action ID may repeat. Capture
  ends with the first failing expectation; later appends are rejected
- `validate(record, expected_identity) -> {ok, final_hash, failure_step, steps}`
  verifies schema, exact caller identity, consecutive indexes, action IDs, complete
  state-delta/hash chain and failure termination before any game action occurs
- `verify_initial(record, state)` checks the state after the game-owned fresh reset
- `verify_before(record, index, state)` checks the actual state before an action
- `verify_after(record, index, state, actual_expectation={})` checks the actual
  state and exact expectation result; success includes `expectation_failed`
- `verify(record, expected_identity, reset, apply, snapshot, check=Callable())`
  offers a synchronous loop. `reset(seed, initial_state)` and
  `apply(action_id, action)` must return `{ok: true}` on success; `snapshot()`
  returns a semantic Dictionary. Optional `check(action_id, action)` returns the
  actual expectation Dictionary. The result includes `steps`, `failure_step` and
  `expectation_failed`

`action`, root semantic state and expectation are Dictionaries. Empty expectation
means `{"ok": true}`. A nonempty expectation must contain a boolean `ok`; any
additional JSON-domain details belong to the adapter and are compared exactly.
Use deterministic IDs/codes/values, not timestamps or unstable error strings.
Expectations should compute truth from current game state, not copy the record.

A record ending in an invariant failure can replay exactly: `{ok: true,
expectation_failed: true, failure_step: 6}` means the failure was faithfully
reproduced. `{ok: false, step_index: 6, error: "after state mismatch", ...}` means
replay diverged there. After-state mismatch diagnostics include expected/actual
hashes and the recorded before/after delta. Adapter reset/apply failures are
execution failures. Callbacks must not throw; engine script errors are outside
this helper's error-return protocol and must also fail the surrounding runner.

### Asynchronous UI/game adapter

The synchronous convenience cannot await UI, movement, animation or dialogue.
Use the per-step methods around the game's existing real action paths:

```gdscript
var validation = Replay.validate(record, independently_computed_identity)
if not validation.ok:
    return validation
await adapter.fresh_start(int(record.seed), record.initial_state.duplicate(true))
var outcome = Replay.verify_initial(record, adapter.snapshot())
if not outcome.ok:
    return outcome
for index in record.steps.size():
    var step = record.steps[index]
    outcome = Replay.verify_before(record, index, adapter.snapshot())
    if not outcome.ok:
        return outcome
    await adapter.apply_real_action(step.action_id, step.action.duplicate(true))
    outcome = Replay.verify_after(record, index, adapter.snapshot(), adapter.expectation())
    if not outcome.ok:
        return outcome
```

The adapter must check its own fresh-start/action results. The low-level methods
revalidate record structure, but have no independent identity source. Always call
`validate(record, independently_computed_identity)` first, before any reset or
side effect. Do not read the expected identity from the record being replayed.
Do not mutate the record during replay. Adapter callbacks get deep copies in the
synchronous convenience so they cannot accidentally rewrite captured evidence.

## Identity and record contract

Schema version 1 has exactly `schema_version`, `identity`, `seed`, `initial_state`,
`initial_hash` and `steps`. An incompatible schema is rejected; there is no implicit
migration. Identity requires lowercase 64-character SHA-256 strings named:

- `tool`: selected replay tool implementation/version
- `content`: all game definitions and configuration relevant to the trace
- `build`: the actual game/adapter implementation used by the trace
- `engine`: the pinned engine identity relevant to determinism

An optional `versions` Dictionary may contain descriptive version labels. It is
also compared exactly. Unknown identity, record, step and delta fields are
rejected, rather than silently ignored. Hash generation and comprehensive inputs
are caller-owned. File names alone, labels alone, timestamps, an arbitrary Git
branch, or reading identity back from the record do not establish actual build
identity. The neutral example hashes the helper, adapter source, fixed synthetic
content descriptor and engine version-info descriptor; it is not a general
project/build manifest generator.

Each step stores exactly `index`, `action_id`, `action`, `before_hash`, `after_hash`,
`delta` and `expectation`. The delta is an array sorted by top-level String key.
Each entry has `key`, `before_present`, `before`, `after_present`, `after`.
Presence flags distinguish an absent key from explicit null. An absent value must
be null. Arrays and nested dictionaries are replaced atomically as whole values;
there is no JSON Pointer/JSON Patch or array-index mutation convention. No-op,
duplicate, out-of-order and inconsistent delta entries are rejected.

Stable action IDs identify game-defined actions and can repeat (for example `wait`
or `travel`). The consecutive `index` identifies the occurrence. The helper does
not deduplicate or retry real gameplay commands. Game command IDs for idempotence
can be represented separately in the game-owned action payload.

The seed is recorded but does not automatically seed Godot's global RNG or capture
an RNG stream. Adapters own RNG initialization and any random-state representation
needed for determinism. The example records generated concrete action payloads;
replay consumes them rather than rerunning an explorer. Reset must reproduce the
recorded initial semantic state. This is not save/restore coverage unless the
adapter deliberately exercises and validates its own save/restore implementation.

## Canonical JSON domain

The supported values are exact Godot `null`, `bool`, `String`, `int`, `float`,
`Array`, and Dictionaries whose keys are exact `String` values:

- Integers must be within `[-9007199254740991, 9007199254740991]` (JSON-safe ±(2^53−1))
- Floats must be finite and in the same magnitude range. Integral floats serialize
  identically to integers, including `-0.0` becoming `0`; nonintegral floats use
  Godot 4.6.3 `JSON.stringify(..., full_precision=true)` for binary64 round trips
- NaN, infinities, StringName, vectors, colors, objects/resources, packed arrays
  and non-String dictionary keys are rejected; adapters must normalize them
- Godot dot assignment of a **new** dictionary field creates a StringName key.
  Construct literal String-keyed dictionaries or use `state["new_key"] = value`
- Dictionary keys sort with Godot String ordering; arrays retain their order.
  Strings use Godot JSON escaping and preserve Unicode without normalization.
  Whitespace is absent. No timestamp, path, platform locale or hash-map insertion
  order participates. This is a versioned Godot canonical format, not RFC 8785
- The entire serialized value/record must not exceed 64 levels of nesting.
  Cycles fail that check; shared acyclic collections serialize by value

JSON decoding yields integral floats in Godot; normalization deliberately makes
those equivalent to the source integers. Booleans are never treated as numbers.
Use `JSON.new().parse(...)` and check the parser result before validation; the
helper accepts a parsed Dictionary, not raw bytes. Decimal money and large RNG
state integers should be represented as deliberate strings or smaller integer
units under an adapter-owned schema. Every accepted fractional number is hashed
exactly; no epsilon tolerance is silently introduced.

This is a small trusted regression helper. SHA-256 values detect inconsistent state
chains but are not signatures; an editor can change a trace and recompute its
hashes. It does not authenticate recordings, sandbox adapters, enforce file-size
limits, prevent external side effects, or prove cross-engine/platform determinism.
Identity must match; different engine builds/backends need explicitly tested
compatibility. Validation deliberately rechecks the complete trace on each public
operation; use it for bounded regression records, not high-volume telemetry.
