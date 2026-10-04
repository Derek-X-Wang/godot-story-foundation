# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
extends Control
## Consumer-owned command -> time/update -> actual Label boundary. No core edit.
const Kernel = preload("res://addons/story_foundation/runtime/rule_kernel.gd")
var world := Kernel.new()
var label := Label.new()
var history: Array = []
var mutation := ""

func _init() -> void:
    add_child(label)

func reset() -> Dictionary:
    world.configure({"version": 1, "actors": [], "initial_scene": "display_room", "initial_inventory": {},
        "initial_facts": {"prepared": false, "deferred": false, "published": false, "closed": false},
        "rules": [
            {"id": "start", "event": "start", "effects": [{"op": "timer", "delay": 3, "event": {"type": "close"}}]},
            {"id": "close", "event": "close", "effects": [{"op": "fact", "key": "closed", "value": true}]},
            {"id": "prepare", "event": "prepare", "when": [{"op": "fact_eq", "key": "prepared", "value": false}],
                "effects": [{"op": "fact", "key": "prepared", "value": true}]},
            {"id": "defer", "event": "defer", "when": [{"op": "fact_eq", "key": "deferred", "value": false}],
                "effects": [{"op": "fact", "key": "deferred", "value": true}]},
            {"id": "publish", "event": "publish", "when": [{"op": "fact_eq", "key": "prepared", "value": true},
                {"op": "fact_eq", "key": "closed", "value": false}, {"op": "fact_eq", "key": "published", "value": false}],
                "effects": [{"op": "fact", "key": "published", "value": true}]}]}, 0)
    history = []
    label.text = "Draft"
    return world.dispatch_command({"id": "start", "type": "start"})

func snapshot() -> Dictionary:
    # The selected kernel's save representation is JSON. This explicit adapter
    # normalizes its StringName dictionary keys to Strings for Replay.canonical.
    return JSON.parse_string(JSON.stringify({"world": world.snapshot(), "history": history, "label": label.text}))

func restore(saved: Dictionary) -> Dictionary:
    var result: Dictionary = world.restore(saved.world)
    if not result.ok: return result
    history = saved.history.duplicate()
    label.text = saved.label
    return {"ok": true}

func step(action: String) -> Dictionary:
    # Both live sample execution and BFS call this very same consumer boundary.
    var result: Dictionary = world.dispatch_command({"id": "command_%d" % history.size(), "type": action})
    if not result.ok:
        if mutation == "false_success" and action == "publish": label.text = "Published"
        if result.error not in ["command_unavailable", "unknown_command"]: return result
        return {"ok": true, "accepted": false}
    if result.get("duplicate", false): return {"ok": false, "error": "duplicate_command"}
    var cost: Dictionary = world.dispatch({"id": "cost_%d" % history.size(), "type": "advance", "amount": 1})
    if not cost.ok or cost.get("duplicate", false): return {"ok": false, "error": "cost_failed"}
    history.append(action)
    if mutation != "stale_projection": label.text = "Published" if world.world_fact("published") else "Draft"
    return {"ok": true, "accepted": true}

static func contract() -> Dictionary:
    return {"name": "kernel_projection", "actions": ["prepare", "defer", "publish"],
        "required_goals": ["published", "deferred_then_published_at_cutoff"], "max_depth": 4, "max_states": 128}

static func observe(current: Dictionary) -> Dictionary:
    var goals: Array = []
    var violations: Array = []
    var facts: Dictionary = current.world.facts
    if facts.published:
        goals.append("published")
        if facts.deferred and facts.closed and current.world.clock == 3 and \
                current.history.find("defer") < current.history.find("publish"):
            goals.append("deferred_then_published_at_cutoff")
        if current.label != "Published": violations.append("committed_state_reaches_label")
    elif current.label == "Published":
        violations.append("rejection_must_not_render_success")
    return {"goals": goals, "violations": violations}
