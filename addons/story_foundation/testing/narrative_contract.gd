# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
extends RefCounted
## Optional test-only bounded BFS. The adapter owns state, real actions and intent.
## The only dependency is the sibling replay helper's strict canonical JSON domain.
const Replay = preload("replay_record.gd")

## Callbacks: reset()->{ok}, snapshot()->Dictionary, restore(snapshot)->{ok},
## step(action_id)->{ok, accepted}, observe(snapshot)->{goals:[], violations:[]}.
## An unavailable command is ok=true/accepted=false, not an execution error.
static func explore(spec: Dictionary, reset: Callable, snapshot: Callable,
        restore: Callable, step: Callable, observe: Callable) -> Dictionary:
    var invalid := _spec_error(spec)
    if not invalid.is_empty(): return _error(invalid)
    for callback: Callable in [reset, snapshot, restore, step, observe]:
        if not callback.is_valid(): return _error("invalid callback")
    var reset_result: Variant = reset.call()
    if not _ok(reset_result): return _error("reset failed")
    var initial := _capture(snapshot)
    if not initial.ok: return initial
    var queue: Array = [{"state": initial.state, "key": initial.key, "trace": []}]
    var seen: Dictionary = {initial.key: true}
    var reached: Dictionary = {}
    var violations: Dictionary = {}
    var cursor := 0
    var accepted := 0
    var rejected := 0
    var observations := 0
    var depth_frontier := 0
    var state_limit_hit := false
    while cursor < queue.size() and not state_limit_hit:
        var entry: Dictionary = queue[cursor]
        cursor += 1
        var loaded := _load(entry, restore, snapshot)
        if not loaded.ok: return _error(loaded.error, entry.trace)
        var observed := _observe(observe, entry.state, spec.required_goals)
        if not observed.ok: return _error(observed.error, entry.trace)
        observations += 1
        _collect(observed, entry.trace, reached, violations)
        if entry.trace.size() >= spec.max_depth:
            depth_frontier += 1
            continue
        for action: String in spec.actions:
            loaded = _load(entry, restore, snapshot)
            if not loaded.ok: return _error(loaded.error, entry.trace)
            var trace: Array = entry.trace.duplicate()
            trace.append(action)
            var result: Variant = step.call(action)
            if not _ok(result) or not result.get("accepted", null) is bool:
                return _error("step failed or omitted boolean accepted: " + action, trace)
            var after := _capture(snapshot)
            if not after.ok: return _error(after.error, trace)
            if not result.accepted:
                rejected += 1
                if after.key != entry.key:
                    _note(violations, "rejected_action_changed_state:" + action, trace)
                # Check the actual post-rejection projection too. A transaction
                # can reject correctly while a consumer renders false success.
                observed = _observe(observe, after.state, spec.required_goals)
                if not observed.ok: return _error(observed.error, trace)
                observations += 1
                _collect(observed, trace, {}, violations)
                continue
            accepted += 1
            if seen.has(after.key): continue
            if seen.size() >= spec.max_states:
                state_limit_hit = true
                break
            seen[after.key] = true
            queue.append({"state": after.state, "key": after.key, "trace": trace})
    # A cap can interrupt a parent's edges after a rejected depth-(d+1)
    # violation but before an already-retained depth-d state is observed. Drain
    # those observations (never new edges) before claiming shortest witnesses.
    while cursor < queue.size():
        var entry: Dictionary = queue[cursor]
        cursor += 1
        var loaded := _load(entry, restore, snapshot)
        if not loaded.ok: return _error(loaded.error, entry.trace)
        var observed := _observe(observe, entry.state, spec.required_goals)
        if not observed.ok: return _error(observed.error, entry.trace)
        observations += 1
        _collect(observed, entry.trace, reached, violations)
        if entry.trace.size() >= spec.max_depth: depth_frontier += 1
    var missing: Array = []
    for goal: String in spec.required_goals:
        if not reached.has(goal): missing.append(goal)
    var complete := not state_limit_hit
    var status := "bounded_pass"
    if not violations.is_empty() or (complete and not missing.is_empty()):
        status = "contract_failed"
    elif not complete:
        status = "inconclusive"
    return {"ok": true, "schema_version": 1, "name": spec.name,
        "status": status, "passed": status == "bounded_pass", "complete_to_depth": complete,
        "actions": spec.actions.duplicate(), "required_goals": spec.required_goals.duplicate(),
        "max_depth": spec.max_depth, "max_states": spec.max_states,
        "states": seen.size(), "expanded": cursor, "accepted_edges": accepted,
        "rejected_edges": rejected, "observations": observations,
        "depth_frontier": depth_frontier, "state_limit_hit": state_limit_hit,
        "shortest_goal_traces": reached, "missing_goals_within_bound": missing,
        "shortest_counterexamples": violations.values(),
        "scope": "Exact supplied snapshots; declared macro actions from reset only. " +
            "Shortest means macro-action count. Bounds are not global impossibility proofs."}

static func _capture(snapshot: Callable) -> Dictionary:
    var state: Variant = snapshot.call()
    if not state is Dictionary: return _error("snapshot must be a Dictionary")
    var encoded := Replay.canonical(state)
    if not encoded.ok: return _error("snapshot: " + str(encoded.error))
    # Store exact canonical bytes as the key, rather than a lossy fact projection
    # or a hash whose collisions would silently merge states.
    return {"ok": true, "state": state.duplicate(true), "key": encoded.json}

static func _load(entry: Dictionary, restore: Callable, snapshot: Callable) -> Dictionary:
    if not _ok(restore.call(entry.state.duplicate(true))): return _error("restore failed")
    var actual := _capture(snapshot)
    if not actual.ok: return actual
    if actual.key != entry.key: return _error("restore did not reproduce the exact snapshot")
    return {"ok": true}

static func _observe(observe: Callable, state: Dictionary, required: Array) -> Dictionary:
    var result: Variant = observe.call(state.duplicate(true))
    if not result is Dictionary or not _strings(result.get("goals")) or not _strings(result.get("violations")):
        return _error("observe requires unique String arrays goals and violations")
    for goal: String in result.goals:
        if goal not in required: return _error("undeclared observed goal: " + goal)
    return {"ok": true, "goals": result.goals, "violations": result.violations}

static func _collect(observed: Dictionary, trace: Array, reached: Dictionary, violations: Dictionary) -> void:
    for goal: String in observed.goals:
        if not reached.has(goal): reached[goal] = trace.duplicate()
    for violation: String in observed.violations:
        _note(violations, violation, trace)

static func _note(violations: Dictionary, requirement: String, trace: Array) -> void:
    # Rejected edges are checked while expanding their parent. A same-depth
    # queued state's invariant may arrive later, so retain the shorter trace.
    if not violations.has(requirement) or trace.size() < violations[requirement].trace.size():
        violations[requirement] = {"requirement": requirement, "trace": trace.duplicate()}

static func _ok(value: Variant) -> bool:
    return value is Dictionary and value.get("ok", null) is bool and value.ok

static func _strings(value: Variant) -> bool:
    if not value is Array: return false
    var seen: Dictionary = {}
    for item: Variant in value:
        if not item is String or item.is_empty() or seen.has(item): return false
        seen[item] = true
    return true

static func _spec_error(spec: Dictionary) -> String:
    var fields := ["name", "actions", "required_goals", "max_depth", "max_states"]
    if spec.size() != fields.size(): return "invalid spec fields"
    for field: String in fields:
        if not spec.has(field): return "missing spec field: " + field
    if not spec.name is String or spec.name.is_empty(): return "name must be nonempty"
    if not _strings(spec.actions) or spec.actions.is_empty(): return "actions must be nonempty unique Strings"
    if not _strings(spec.required_goals) or spec.required_goals.is_empty(): return "required_goals must be nonempty unique Strings"
    if not spec.max_depth is int or spec.max_depth < 0: return "max_depth must be a nonnegative int"
    if not spec.max_states is int or spec.max_states < 1: return "max_states must be a positive int"
    return ""

static func _error(message: String, trace: Array = []) -> Dictionary:
    return {"ok": false, "passed": false, "status": "execution_error", "error": message,
        "trace": trace.duplicate()}
