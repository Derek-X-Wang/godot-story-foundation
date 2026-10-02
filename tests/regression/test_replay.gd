# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
extends SceneTree

const Replay = preload("res://replay_record.gd")
var checks := 0
var failures: Array[String] = []
var adapter_state: Dictionary = {}
var reset_calls := 0
var apply_calls := 0
var break_adapter := false

func check(condition: bool, label: String) -> void:
    checks += 1
    if not condition: failures.append(label)

func identity() -> Dictionary:
    return {"tool": "tool-v1".sha256_text(), "content": "content-v1".sha256_text(),
        "build": "build-v1".sha256_text(), "engine": "engine-v1".sha256_text()}

func _initialize() -> void:
    canonical_checks()
    record_checks()
    adapter_checks()
    if failures.is_empty():
        print("Replay helper: %d checks passed" % checks)
        quit(0)
    else:
        for failure: String in failures: printerr("FAIL: " + failure)
        print("Replay helper: %d/%d checks failed" % [failures.size(), checks])
        quit(1)

func canonical_checks() -> void:
    var a: Dictionary = Replay.canonical({"z": [1, true, null], "a": {"b": 1.25, "a": "雪\n\""}})
    var b: Dictionary = Replay.canonical({"a": {"a": "雪\n\"", "b": 1.25}, "z": [1.0, true, null]})
    check(a.ok and a.json == b.json and a.hash == b.hash, "canonical sorted keys and integer/float normalization")
    check(Replay.canonical(-0.0).json == "0", "negative zero normalized")
    check(Replay.canonical({}).json == "{}" and Replay.canonical([]).json == "[]", "empty collections")
    check(Replay.canonical("a").hash == JSON.stringify("a").sha256_text(), "UTF-8 SHA-256")
    for number: Variant in [9007199254740991, -9007199254740991, 0.1, 1.23456789012345, 0.000001, 12345678.125, 1e-200, 1e-20, 0.9999999999999999, 5e-324]:
        var encoded: Dictionary = Replay.canonical(number)
        var roundtrip: Dictionary = Replay.canonical(JSON.parse_string(encoded.json))
        check(encoded.ok and roundtrip.ok and encoded.json == roundtrip.json and JSON.parse_string(encoded.json) == number, "canonical numeric JSON roundtrip: " + str(number))
    for invalid: Variant in [NAN, INF, -INF, 9007199254740992, -9007199254740992,
            Vector2.ONE, Color.RED, PackedStringArray(["a"]), {1: "not a string key"}, &"StringName"]:
        check(not Replay.canonical(invalid).ok, "unsupported primitive rejected")
    var nested: Variant = null
    for _index in 66: nested = [nested]
    check(not Replay.canonical(nested).ok, "excessive nesting rejected")
    var cyclic := []
    cyclic.append(cyclic)
    check(not Replay.canonical(cyclic).ok, "cycle rejected without recursive crash")
    cyclic.clear()

func record_checks() -> void:
    var ids := identity()
    var initial := {"count": 0, "remove": true, "nested": {"a": 1}}
    var started: Dictionary = Replay.begin(ids, 42, initial)
    check(started.ok, "begin valid record")
    var record: Dictionary = started.record
    initial.count = 99
    ids.tool = "changed"
    check(record.initial_state.count == 0 and record.identity.tool == identity().tool, "begin takes owned copies")
    var before := {"count": 0, "remove": true, "nested": {"a": 1}}
    var after := {"count": 1, "new": null, "nested": {"a": 2}}
    var action := {"kind": "set", "value": 1}
    var appended: Dictionary = Replay.append_step(record, "action:0", action, before, after)
    check(appended.ok and appended.step_index == 0, "append valid step")
    check(record.steps[0].delta.size() == 4, "delta has changed, removed and explicitly null keys")
    check(record.steps[0].delta[0].key == "count" and record.steps[0].delta[3].key == "remove", "delta sorted")
    after.nested.a = 99
    action.value = 99
    check(record.steps[0].delta[1].after.a == 2 and record.steps[0].action.value == 1, "append owns deep copies")
    check(Replay.validate(record, identity()).ok, "strict record valid")
    var json: String = Replay.canonical(record).json
    var parsed: Dictionary = JSON.parse_string(json)
    check(Replay.validate(parsed, identity()).ok, "JSON parsed record valid")
    check(Replay.canonical(parsed).json == json, "record canonical roundtrip exact")
    check(Replay.verify_initial(record, before).ok, "verify initial")
    check(Replay.verify_before(record, 0, before).ok, "verify before")
    check(not Replay.verify_before(record, 0, {"count": 8}).ok, "before divergence rejected")
    check(Replay.verify_after(record, 0, {"count": 1, "new": null, "nested": {"a": 2}}).ok, "verify after")
    check(not Replay.verify_after(record, 0, before).ok, "after divergence rejected")
    check(not Replay.verify_before(record, -1, before).ok and not Replay.verify_after(record, 1, before).ok, "bad step index")
    var unchanged: String = Replay.canonical(record).json
    var repeated: Dictionary = Replay.begin(identity(), 42, {"count": 0}).record
    check(Replay.append_step(repeated, "wait", {}, {"count": 0}, {"count": 0}).ok, "first repeated action capture")
    check(Replay.append_step(repeated, "wait", {}, {"count": 0}, {"count": 0}).ok, "same stable gameplay action ID may repeat")
    check(Replay.validate(repeated, identity()).ok and repeated.steps[1].index == 1, "step index identifies repeated occurrence")
    check(not Replay.append_step(record, "action:1", {}, {}, {}).ok, "discontinuous before state rejected")
    check(Replay.canonical(record).json == unchanged, "rejected append is atomic")
    for field: String in ["tool", "content", "build", "engine"]:
        var changed := identity()
        changed[field] = "new".sha256_text()
        check(not Replay.validate(record, changed).ok, "changed identity rejected: " + field)
    var bad_identity := identity()
    bad_identity.tool = "0".repeat(63)
    check(not Replay.begin(bad_identity, 1, {}).ok, "malformed digest rejected")
    bad_identity = identity()
    bad_identity.extra = "unknown"
    check(not Replay.begin(bad_identity, 1, {}).ok, "unknown identity field rejected")
    var versioned := identity()
    versioned["versions"] = {"fixture": "1"}
    var version_result: Dictionary = Replay.begin(versioned, 1, {})
    check(version_result.ok, "optional descriptive versions")
    for mutation in 13:
        var bad := record.duplicate(true)
        match mutation:
            0: bad.schema_version = 2
            1: bad.extra = true
            2: bad.initial_state.count = 500
            3: bad.steps[0].index = 4
            4: bad.steps[0].before_hash = "bad"
            5: bad.steps[0].after_hash = "bad"
            6: bad.steps[0].delta[0].before = 8
            7: bad.steps[0].delta.reverse()
            8: bad.steps[0].delta[2].before = 8
            9: bad.steps[0].expectation = {"ok": 1}
            10: bad.steps[0].action = "not a Dictionary"
            11: bad.steps[0].extra = true
            12: bad.steps[0].delta[0].extra = true
        check(not Replay.validate(bad, identity()).ok, "malformed record rejected: %d" % mutation)
    check(not Replay.validate([], identity()).ok, "non-dictionary record rejected")

func adapter_checks() -> void:
    var record: Dictionary = Replay.begin(identity(), 99, {"count": 0}).record
    check(Replay.append_step(record, "set", {"value": 2}, {"count": 0}, {"count": 2}).ok, "adapter first step captured")
    check(Replay.append_step(record, "set", {"value": 3}, {"count": 2}, {"count": 3},
        {"ok": false, "id": "must-be-even", "actual": 3}).ok, "expectation failure captured")
    check(not Replay.append_step(record, "set:2", {}, {"count": 3}, {"count": 3}).ok, "failure terminates record")
    var result: Dictionary = Replay.verify(record, identity(), reset_adapter, apply_adapter, snapshot, expectation)
    check(result.ok and result.expectation_failed and result.failure_step == 1, "exact failure reproduced at index 1")
    check(reset_calls == 1 and apply_calls == 2, "real adapter callbacks run")
    var replay_again: Dictionary = Replay.verify(record, identity(), reset_adapter, apply_adapter, snapshot, expectation)
    check(replay_again == result and adapter_state.count == 3, "second fresh replay deterministic")
    var invalid := identity()
    invalid.content = "other".sha256_text()
    var resets_before := reset_calls
    var actions_before := apply_calls
    check(not Replay.verify(record, invalid, reset_adapter, apply_adapter, snapshot, expectation).ok, "identity mismatch refuses replay")
    check(reset_calls == resets_before and apply_calls == actions_before, "validation runs before any adapter effects")
    break_adapter = true
    var mismatch: Dictionary = Replay.verify(record, identity(), reset_adapter, apply_adapter, snapshot, expectation)
    check(not mismatch.ok and mismatch.step_index == 0 and mismatch.error == "after state mismatch", "wrong adapter found at first divergence")
    check(mismatch.has("expected_hash") and mismatch.has("actual_hash") and mismatch.has("recorded_delta"), "divergence diagnostics")
    break_adapter = false
    check(not Replay.verify_after(record, 1, {"count": 3}, {"ok": true}).ok, "mismatched expectation rejected")
    var empty_record: Dictionary = Replay.begin(identity(), 0, {}).record
    check(not Replay.verify(empty_record, identity(), Callable(), apply_adapter, snapshot).ok, "invalid callback rejected")
    check(Replay.verify(empty_record, identity(), reset_adapter, apply_adapter, snapshot).ok, "empty replay verifies initial state")
    var no_failure: Dictionary = Replay.begin(identity(), 0, {"count": 0}).record
    Replay.append_step(no_failure, "set", {"value": 2}, {"count": 0}, {"count": 2})
    var success: Dictionary = Replay.verify(no_failure, identity(), reset_adapter, apply_adapter, snapshot)
    check(success.ok and not success.expectation_failed and success.failure_step == -1, "successful record replay")

func reset_adapter(_seed: int, initial: Dictionary) -> Dictionary:
    reset_calls += 1
    adapter_state = initial.duplicate(true)
    return {"ok": true}

func apply_adapter(_id: String, action: Dictionary) -> Dictionary:
    apply_calls += 1
    adapter_state.count = int(action.value) + (1 if break_adapter else 0)
    return {"ok": true}

func snapshot() -> Dictionary:
    return adapter_state.duplicate(true)

func expectation(_id: String, _action: Dictionary) -> Dictionary:
    if adapter_state.count % 2 == 0: return {"ok": true}
    return {"ok": false, "id": "must-be-even", "actual": adapter_state.count}
