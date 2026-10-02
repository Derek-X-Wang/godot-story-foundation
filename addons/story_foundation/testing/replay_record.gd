# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
extends RefCounted
## Independently optional semantic replay records. No game/runtime/autoload dependency.
## See docs/replay.md for the restricted JSON domain and adapter-owned lifecycle.

const SCHEMA_VERSION := 1
const MAX_SAFE_INTEGER := 9007199254740991
const MAX_DEPTH := 64
const IDENTITY_KEYS := ["tool", "content", "build", "engine"]
const RECORD_KEYS := ["schema_version", "identity", "seed", "initial_state", "initial_hash", "steps"]
const STEP_KEYS := ["index", "action_id", "action", "before_hash", "after_hash", "delta", "expectation"]
const DELTA_KEYS := ["key", "before_present", "before", "after_present", "after"]

## Canonical UTF-8 JSON and SHA-256. Never stringifies arbitrary Godot objects.
static func canonical(value: Variant) -> Dictionary:
    var result := _canonical(value, 0)
    if result.ok:
        result["hash"] = result.json.sha256_text()
    return result

## identity requires four lowercase SHA-256 strings; optional versions is a dict.
static func begin(identity: Dictionary, seed_value: int, initial_state: Dictionary) -> Dictionary:
    var error := _identity_error(identity)
    if not error.is_empty(): return _failure(error)
    if not _safe_integer(seed_value): return _failure("seed must be a JSON-safe integer")
    var initial := canonical(initial_state)
    if not initial.ok: return initial
    var record := {
        "schema_version": SCHEMA_VERSION, "identity": identity.duplicate(true),
        "seed": seed_value, "initial_state": initial_state.duplicate(true),
        "initial_hash": initial.hash, "steps": [],
    }
    var encoded := canonical(record)
    if not encoded.ok: return encoded
    return {"ok": true, "record": record}

## Atomic append: validate first; snapshots, action and expectation are deep-copied.
## A failing expectation terminates a trace. Indexes are zero-based.
static func append_step(record: Dictionary, action_id: String, action: Dictionary,
        before_state: Dictionary, after_state: Dictionary, expectation: Dictionary = {}) -> Dictionary:
    var validated := _validate_self(record)
    if not validated.ok: return validated
    if validated.failure_step >= 0: return _failure("cannot append after expectation failure")
    if action_id.is_empty(): return _failure("action_id must be nonempty")
    var action_value := canonical(action)
    if not action_value.ok: return action_value
    var expected := _expectation(expectation)
    if not expected.ok: return expected
    var before := canonical(before_state)
    if not before.ok: return before
    var after := canonical(after_state)
    if not after.ok: return after
    if before.hash != validated.final_hash:
        return _failure("before_state does not continue the recorded state")
    var index: int = record.steps.size()
    var candidate := record.duplicate(true)
    candidate.steps.append({
        "index": index, "action_id": action_id, "action": action.duplicate(true),
        "before_hash": before.hash, "after_hash": after.hash,
        "delta": _delta(before_state, after_state), "expectation": expected.value,
    })
    var candidate_result := validate(candidate, record.identity)
    if not candidate_result.ok: return candidate_result
    record.steps.append(candidate.steps.back())
    return {"ok": true, "step_index": index}

## Strict schema + exact caller identity + complete delta/hash-chain validation.
## This is integrity checking, not authentication or an untrusted-input sandbox.
static func validate(record: Variant, expected_identity: Dictionary) -> Dictionary:
    var expected_error := _identity_error(expected_identity)
    if not expected_error.is_empty(): return _failure("expected identity: " + expected_error)
    var encoded := canonical(record)
    if not encoded.ok: return encoded
    if not record is Dictionary or not _exact_keys(record, RECORD_KEYS):
        return _failure("invalid replay record fields")
    if not _safe_integer(record.schema_version) or record.schema_version != SCHEMA_VERSION:
        return _failure("unsupported replay schema_version")
    if not record.identity is Dictionary: return _failure("identity must be a Dictionary")
    var identity_error := _identity_error(record.identity)
    if not identity_error.is_empty(): return _failure(identity_error)
    if canonical(record.identity).json != canonical(expected_identity).json:
        return _failure("replay identity mismatch")
    if not _safe_integer(record.seed): return _failure("seed must be a JSON-safe integer")
    if not record.initial_state is Dictionary or not record.steps is Array:
        return _failure("initial_state must be a Dictionary and steps an Array")
    var state: Dictionary = record.initial_state.duplicate(true)
    var state_hash: String = canonical(state).hash
    if record.initial_hash != state_hash: return _failure("initial_state hash mismatch")
    var failure_step := -1
    for index in record.steps.size():
        var step: Variant = record.steps[index]
        if not step is Dictionary or not _exact_keys(step, STEP_KEYS):
            return _failure("invalid step fields", index)
        if not _safe_integer(step.index) or step.index != index:
            return _failure("step index must be consecutive", index)
        if not step.action_id is String or step.action_id.is_empty():
            return _failure("action_id must be a nonempty String", index)
        if not step.action is Dictionary or not step.delta is Array or not step.expectation is Dictionary:
            return _failure("invalid action, delta or expectation type", index)
        var expected := _expectation(step.expectation)
        if not expected.ok or step.expectation.is_empty(): return _failure("expectation requires boolean ok", index)
        if failure_step >= 0: return _failure("steps cannot follow an expectation failure", index)
        if not step.expectation.ok: failure_step = index
        if step.before_hash != state_hash: return _failure("before_hash chain mismatch", index)
        var applied := _apply_delta(state, step.delta)
        if not applied.ok: return _failure(applied.error, index)
        state = applied.state
        state_hash = canonical(state).hash
        if step.after_hash != state_hash: return _failure("after_hash does not match delta", index)
    return {"ok": true, "final_hash": state_hash, "failure_step": failure_step, "steps": record.steps.size()}

## For async adapters: validate identity before reset or applying any game action.
static func verify_initial(record: Dictionary, state: Dictionary) -> Dictionary:
    var validated := _validate_self(record)
    if not validated.ok: return validated
    return _compare_state(record.initial_hash, state, -1, "initial")

static func verify_before(record: Dictionary, index: int, state: Dictionary) -> Dictionary:
    var validated := _validate_index(record, index)
    if not validated.ok: return validated
    return _compare_state(record.steps[index].before_hash, state, index, "before")

## A reproduced expectation failure is an exact replay success, explicitly flagged.
## Callers must distinguish result.ok from expectation_failed in CI/exit policy.
static func verify_after(record: Dictionary, index: int, state: Dictionary,
        actual_expectation: Dictionary = {}) -> Dictionary:
    var validated := _validate_index(record, index)
    if not validated.ok: return validated
    var compared := _compare_state(record.steps[index].after_hash, state, index, "after")
    if not compared.ok:
        compared["recorded_delta"] = record.steps[index].delta.duplicate(true)
        return compared
    var expected := _expectation(actual_expectation)
    if not expected.ok: return expected
    if canonical(expected.value).json != canonical(record.steps[index].expectation).json:
        return _failure("expectation result mismatch", index)
    return {"ok": true, "step_index": index, "expectation_failed": not expected.value.ok}

## Synchronous convenience. All three callbacks must return dictionaries:
## reset(seed, initial_state) -> {ok}; apply(action_id, action) -> {ok};
## snapshot() -> semantic state. Optional check(action_id, action) -> {ok, ...}.
## Errors in adapter code, asynchronous actions and external effects remain owned
## by the adapter; asynchronous integrations use the verification methods above.
static func verify(record: Dictionary, expected_identity: Dictionary, reset: Callable,
        apply: Callable, snapshot: Callable, check: Callable = Callable()) -> Dictionary:
    var validated := validate(record, expected_identity)
    if not validated.ok: return validated
    if not reset.is_valid() or not apply.is_valid() or not snapshot.is_valid():
        return _failure("reset, apply and snapshot must be valid Callables")
    var reset_result: Variant = reset.call(int(record.seed), record.initial_state.duplicate(true))
    if not _callback_ok(reset_result): return _failure("adapter reset failed")
    var state: Variant = snapshot.call()
    if not state is Dictionary: return _failure("snapshot must return a Dictionary")
    var initial := verify_initial(record, state)
    if not initial.ok: return initial
    for index in record.steps.size():
        var step: Dictionary = record.steps[index]
        state = snapshot.call()
        if not state is Dictionary: return _failure("snapshot must return a Dictionary", index)
        var before := verify_before(record, index, state)
        if not before.ok: return before
        var applied: Variant = apply.call(step.action_id, step.action.duplicate(true))
        if not _callback_ok(applied): return _failure("adapter action failed", index)
        var expectation: Variant = check.call(step.action_id, step.action.duplicate(true)) if check.is_valid() else {}
        if not expectation is Dictionary: return _failure("check must return a Dictionary", index)
        state = snapshot.call()
        if not state is Dictionary: return _failure("snapshot must return a Dictionary", index)
        var after := verify_after(record, index, state, expectation)
        if not after.ok: return after
    return {"ok": true, "steps": record.steps.size(), "expectation_failed": validated.failure_step >= 0,
        "failure_step": validated.failure_step}

static func _validate_self(record: Dictionary) -> Dictionary:
    if not record.get("identity") is Dictionary: return _failure("identity must be a Dictionary")
    return validate(record, record.identity)

static func _callback_ok(value: Variant) -> bool:
    return value is Dictionary and value.get("ok") is bool and value.ok

static func _validate_index(record: Dictionary, index: int) -> Dictionary:
    var validated := _validate_self(record)
    if not validated.ok: return validated
    if index < 0 or index >= record.steps.size(): return _failure("step index out of range", index)
    return {"ok": true}

static func _compare_state(expected_hash: String, state: Dictionary, index: int, phase: String) -> Dictionary:
    var actual := canonical(state)
    if not actual.ok: return actual
    if actual.hash != expected_hash:
        return {"ok": false, "error": phase + " state mismatch", "step_index": index,
            "expected_hash": expected_hash, "actual_hash": actual.hash}
    return {"ok": true, "step_index": index}

static func _expectation(value: Dictionary) -> Dictionary:
    var encoded := canonical(value)
    if not encoded.ok: return encoded
    var result := value.duplicate(true) if not value.is_empty() else {"ok": true}
    if not result.get("ok") is bool: return _failure("expectation requires boolean ok")
    return {"ok": true, "value": result}

static func _identity_error(identity: Dictionary) -> String:
    for key: Variant in identity:
        if not key is String or (key not in IDENTITY_KEYS and key != "versions"):
            return "unknown identity field"
    for key: String in IDENTITY_KEYS:
        if not identity.get(key) is String or not _is_digest(identity[key]):
            return "identity.%s must be a lowercase SHA-256 digest" % key
    if identity.has("versions") and not identity.versions is Dictionary:
        return "identity.versions must be a Dictionary"
    var encoded := canonical(identity)
    return "" if encoded.ok else encoded.error

static func _is_digest(value: String) -> bool:
    if value.length() != 64: return false
    for character in value:
        if character not in "0123456789abcdef": return false
    return true

static func _exact_keys(value: Dictionary, keys: Array) -> bool:
    if value.size() != keys.size(): return false
    for key: Variant in keys:
        if not value.has(key): return false
    return true

static func _safe_integer(value: Variant) -> bool:
    if value is int: return value >= -MAX_SAFE_INTEGER and value <= MAX_SAFE_INTEGER
    return value is float and is_finite(value) and abs(value) <= MAX_SAFE_INTEGER and floor(value) == value

static func _canonical(value: Variant, depth: int) -> Dictionary:
    if depth > MAX_DEPTH: return _failure("JSON nesting exceeds 64 levels (cycles are unsupported)")
    match typeof(value):
        TYPE_NIL: return {"ok": true, "json": "null"}
        TYPE_BOOL: return {"ok": true, "json": "true" if value else "false"}
        TYPE_STRING: return {"ok": true, "json": JSON.stringify(value)}
        TYPE_INT:
            if not _safe_integer(value): return _failure("integer outside JSON-safe range")
            return {"ok": true, "json": str(value)}
        TYPE_FLOAT:
            if not is_finite(value) or abs(value) > MAX_SAFE_INTEGER:
                return _failure("number must be finite and within JSON-safe range")
            if floor(value) == value: return {"ok": true, "json": str(int(value))}
            return {"ok": true, "json": JSON.stringify(value, "", false, true)}
        TYPE_ARRAY:
            var parts := PackedStringArray()
            for item: Variant in value:
                var encoded := _canonical(item, depth + 1)
                if not encoded.ok: return encoded
                parts.append(encoded.json)
            return {"ok": true, "json": "[" + ",".join(parts) + "]"}
        TYPE_DICTIONARY:
            var keys: Array = value.keys()
            for key: Variant in keys:
                if not key is String: return _failure("JSON dictionary keys must be Strings")
            keys.sort()
            var parts := PackedStringArray()
            for key: String in keys:
                var encoded := _canonical(value[key], depth + 1)
                if not encoded.ok: return encoded
                parts.append(JSON.stringify(key) + ":" + encoded.json)
            return {"ok": true, "json": "{" + ",".join(parts) + "}"}
    return _failure("unsupported JSON primitive type: " + type_string(typeof(value)))

static func _delta(before: Dictionary, after: Dictionary) -> Array:
    var keys := before.keys()
    for key: String in after:
        if not before.has(key): keys.append(key)
    keys.sort()
    var changes := []
    for key: String in keys:
        if before.has(key) == after.has(key) and canonical(before.get(key)).json == canonical(after.get(key)).json:
            continue
        changes.append({"key": key, "before_present": before.has(key), "before": _copy(before.get(key)),
            "after_present": after.has(key), "after": _copy(after.get(key))})
    return changes

static func _apply_delta(original: Dictionary, changes: Array) -> Dictionary:
    var state := original.duplicate(true)
    var previous := ""
    var first := true
    for change: Variant in changes:
        if not change is Dictionary or not _exact_keys(change, DELTA_KEYS): return _failure("invalid delta fields")
        if not change.key is String or not change.before_present is bool or not change.after_present is bool:
            return _failure("invalid delta key or presence flags")
        if not first and change.key <= previous: return _failure("delta keys must be unique and sorted")
        previous = change.key
        first = false
        if not change.before_present and change.before != null: return _failure("absent before value must be null")
        if not change.after_present and change.after != null: return _failure("absent after value must be null")
        if state.has(change.key) != change.before_present or canonical(state.get(change.key)).json != canonical(change.before).json:
            return _failure("delta before value mismatch")
        if change.before_present == change.after_present and canonical(change.before).json == canonical(change.after).json:
            return _failure("redundant delta entry")
        if change.after_present: state[change.key] = _copy(change.after)
        else: state.erase(change.key)
    return {"ok": true, "state": state}

static func _copy(value: Variant) -> Variant:
    return value.duplicate(true) if value is Dictionary or value is Array else value

static func _failure(error: String, index: int = -1) -> Dictionary:
    return {"ok": false, "error": error, "step_index": index}
