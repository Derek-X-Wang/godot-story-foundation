# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
extends SceneTree
const Explorer = preload("res://narrative_contract.gd")
const Adapter = preload("res://neutral_adapter.gd")
var checks := 0
var failures: Array = []

func _initialize() -> void:
    call_deferred("run")

func check(condition: bool, message: String) -> void:
    checks += 1
    if not condition: failures.append(message)

func explore(adapter, spec: Dictionary = {}) -> Dictionary:
    return Explorer.explore(adapter.contract() if spec.is_empty() else spec,
        adapter.reset, adapter.snapshot, adapter.restore, adapter.step, adapter.observe)

func violation(report: Dictionary, id: String) -> Dictionary:
    for item: Dictionary in report.get("shortest_counterexamples", []):
        if item.requirement == id: return item
    return {}

func run() -> void:
    var adapter := Adapter.new()
    var good := explore(adapter)
    check(good.ok and good.passed and good.complete_to_depth, "neutral authored contract passes")
    check(good.shortest_goal_traces.both_ready == ["enable_left", "enable_right"], "shortest goal uses two macros")
    check(good.shortest_goal_traces.deferred_confirmation.size() == 4, "defer then confirm remains reachable")
    check(good.states > 16, "complete history keeps ordering-distinct states separate")
    check(good.rejected_edges > 0, "real unavailable commands were exercised")
    check(good == explore(adapter), "reports are deterministic without elapsed-time noise")
    # Replay the actual shortest goal through the same boundary; never apply deltas.
    adapter.reset()
    for action: String in good.shortest_goal_traces.deferred_confirmation:
        check(adapter.step(action).accepted, "witness executes " + action)
    check("deferred_confirmation" in adapter.observe(adapter.snapshot()).goals, "witness reaches independent goal")
    for mode: String in ["missing_option", "defer_lock"]:
        adapter.mutation = mode
        var failed := explore(adapter)
        check(failed.ok and not failed.passed and failed.status == "contract_failed", "semantic mutation is caught: " + mode)
        check(not failed.missing_goals_within_bound.is_empty(), "mutation removes intended goal: " + mode)
        var requirement := "right_option_required" if mode == "missing_option" else "confirmation_remains_available_after_defer"
        var counter := violation(failed, requirement)
        check(not counter.is_empty(), "mutation has named author requirement: " + mode)
        check(counter.get("trace", []).size() == (0 if mode == "missing_option" else 3), "shortest mutation counterexample: " + mode)
    adapter.mutation = ""
    var limited := adapter.contract()
    limited.max_states = 1
    var cutoff := explore(adapter, limited)
    check(cutoff.status == "inconclusive" and not cutoff.passed and not cutoff.complete_to_depth, "state cap never passes")
    check(cutoff.state_limit_hit and cutoff.states == 1, "state cap is explicit")
    cutoff = Explorer.explore(limited, adapter.reset, adapter.snapshot, adapter.restore, adapter.step,
        func(_s): return {"goals": ["both_ready", "direct_confirmation", "deferred_confirmation"], "violations": []})
    check(cutoff.missing_goals_within_bound.is_empty() and not cutoff.passed and cutoff.status == "inconclusive",
        "even all witnessed goals cannot excuse incomplete invariant exploration")
    limited = adapter.contract()
    limited.max_depth = 0
    cutoff = explore(adapter, limited)
    check(cutoff.status == "contract_failed" and cutoff.complete_to_depth and cutoff.depth_frontier == 1,
        "unmet bounded goal is not a global impossibility claim")
    for field: String in ["actions", "required_goals"]:
        var malformed := adapter.contract()
        malformed[field] = ["same", "same"]
        check(not explore(adapter, malformed).ok, "duplicate IDs rejected: " + field)
    for field: String in ["max_depth", "max_states"]:
        var malformed := adapter.contract()
        malformed[field] = true
        check(not explore(adapter, malformed).ok, "boolean bound rejected: " + field)
    var extra := adapter.contract()
    extra["unknown"] = true
    check(not explore(adapter, extra).ok, "unknown spec fields rejected")
    var spec := adapter.contract()
    check(not Explorer.explore(spec, Callable(), adapter.snapshot, adapter.restore, adapter.step, adapter.observe).ok,
        "invalid callback rejected")
    check(not Explorer.explore(spec, func(): return {"ok": false}, adapter.snapshot, adapter.restore, adapter.step, adapter.observe).ok,
        "reset failure remains execution failure")
    check(not Explorer.explore(spec, adapter.reset, func(): return {"unsupported": Vector2.ZERO}, adapter.restore, adapter.step, adapter.observe).ok,
        "unsupported exact snapshot domain rejected")
    check(not Explorer.explore(spec, adapter.reset, adapter.snapshot, func(_s): return {"ok": false}, adapter.step, adapter.observe).ok,
        "restore failure remains execution failure")
    var bad_restore := func(saved):
        adapter.restore(saved)
        adapter.state.history.append("invented")
        return {"ok": true}
    var bad := Explorer.explore(spec, adapter.reset, adapter.snapshot, bad_restore, adapter.step, adapter.observe)
    check(not bad.ok and bad.error.contains("exact snapshot"), "lying/lossy restore fails closed")
    check(not Explorer.explore(spec, adapter.reset, adapter.snapshot, adapter.restore, func(_a): return {"ok": true}, adapter.observe).ok,
        "missing acceptance outcome rejected")
    check(not Explorer.explore(spec, adapter.reset, adapter.snapshot, adapter.restore, func(_a): return {"ok": false}, adapter.observe).ok,
        "action execution failure never becomes unreachable goal")
    check(not Explorer.explore(spec, adapter.reset, adapter.snapshot, adapter.restore, adapter.step,
        func(_s): return {"goals": ["not_authored"], "violations": []}).ok, "undeclared oracle goal rejected")
    check(not Explorer.explore(spec, adapter.reset, adapter.snapshot, adapter.restore, adapter.step,
        func(_s): return {"goals": [], "violations": [false]}).ok, "malformed oracle rejected")
    var reject_with_change := func(_action):
        adapter.state.history.append("rejected")
        return {"ok": true, "accepted": false}
    bad = Explorer.explore(spec, adapter.reset, adapter.snapshot, adapter.restore, reject_with_change, adapter.observe)
    check(not violation(bad, "rejected_action_changed_state:enable_left").is_empty(), "atomic rejection checked over full snapshot")
    # A fully rejected, unchanged graph must exhaust exactly one state.
    bad = Explorer.explore(spec, adapter.reset, adapter.snapshot, adapter.restore,
        func(_a): return {"ok": true, "accepted": false}, adapter.observe)
    check(bad.states == 1 and bad.complete_to_depth and not bad.passed, "missing transition fails independent goal")
    # No-op acceptance must merge by the complete snapshot, not grow forever.
    bad = Explorer.explore(spec, adapter.reset, adapter.snapshot, adapter.restore,
        func(_a): return {"ok": true, "accepted": true}, adapter.observe)
    check(bad.states == 1 and bad.accepted_edges == 4, "exact no-op deduplicates")
    var capped := CappedFixture.new()
    var capped_spec := {"name": "cap_shortest", "actions": ["first", "short", "reject", "overflow"],
        "required_goals": ["initial"], "max_depth": 3, "max_states": 3}
    var cap_result := Explorer.explore(capped_spec, capped.reset, capped.snapshot, capped.restore, capped.step, capped.observe)
    check(cap_result.state_limit_hit and not cap_result.complete_to_depth and not cap_result.passed,
        "cap stops edges even when all retained observations are drained")
    check(violation(cap_result, "semantic_violation").trace == ["short"],
        "queued shorter state outranks deeper rejected-edge violation at cap")
    capped_spec.max_states = 5
    var full_result := Explorer.explore(capped_spec, capped.reset, capped.snapshot, capped.restore, capped.step, capped.observe)
    check(full_result.complete_to_depth and violation(full_result, "semantic_violation").trace == ["short"],
        "capped and complete traversal agree on shortest semantic counterexample")
    print("NARRATIVE_RESULT " + JSON.stringify({"schema_version": 1, "suite_id": "narrative_units",
        "scenario_ids": ["helper_contract"], "passed": failures.is_empty(), "failures": failures, "checks": checks}))
    quit(0 if failures.is_empty() else 1)

class CappedFixture:
    extends RefCounted
    var state: Dictionary = {}
    func reset() -> Dictionary:
        state = {"position": "root", "violation": false}
        return {"ok": true}
    func snapshot() -> Dictionary:
        return state.duplicate(true)
    func restore(saved: Dictionary) -> Dictionary:
        state = saved.duplicate(true)
        return {"ok": true}
    func step(action: String) -> Dictionary:
        if state.position == "root" and action == "first":
            state.position = "A"
            return {"ok": true, "accepted": true}
        if state.position == "root" and action == "short":
            state = {"position": "B", "violation": true}
            return {"ok": true, "accepted": true}
        if state.position == "A" and action == "reject":
            state.violation = true
            return {"ok": true, "accepted": false}
        if state.position == "A" and action == "overflow":
            state.position = "C"
            return {"ok": true, "accepted": true}
        return {"ok": true, "accepted": false}
    func observe(saved: Dictionary) -> Dictionary:
        return {"goals": ["initial"], "violations": ["semantic_violation"] if saved.violation else []}
