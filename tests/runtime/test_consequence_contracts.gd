# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
extends SceneTree
## Consumer test recipe, not a planner API: replay the real kernel and render via
## the existing village view + Dialogue Manager. All policy/prose is synthetic.
const Kernel = preload("res://addons/story_foundation/runtime/rule_kernel.gd")
const Bridge = preload("res://addons/story_foundation/adapters/dialogue_manager_bridge.gd")
var checks := 0
var failures: Array[String] = []

func _initialize() -> void:
    call_deferred("run")

func check(condition: bool, label: String) -> void:
    checks += 1
    if not condition:
        failures.append(label)
        printerr("FAIL: " + label)

func policy() -> Dictionary:
    return {"version": 1, "actors": [], "initial_scene": "workshop",
        "initial_inventory": {"part": 0},
        "initial_facts": {"closed": false, "completed": false, "missed": false,
            "primary_completed": false, "secondary_checked": false, "secondary_shared": false},
        # This example's costs belong to its consumer, not the Foundation schema.
        "costs": {"prepare": 2, "complete": 3, "broken": 0, "cycle": 0},
        "rules": [
            {"id": "start", "event": "start", "effects": [
                {"op": "timer", "delay": 5, "event": {"type": "deadline"}}]},
            {"id": "close", "event": "deadline", "effects": [
                {"op": "fact", "key": "closed", "value": true}]},
            {"id": "miss", "event": "deadline", "when": [
                {"op": "fact_eq", "key": "completed", "value": false}], "effects": [
                {"op": "fact", "key": "missed", "value": true}]},
            {"id": "prepare", "event": "prepare", "effects": [
                {"op": "inventory", "key": "part", "delta": 1}]},
            {"id": "complete", "event": "complete", "when": [
                {"op": "fact_eq", "key": "closed", "value": false},
                {"op": "inventory_gte", "key": "part", "value": 1}], "effects": [
                {"op": "inventory", "key": "part", "delta": -1},
                {"op": "fact", "key": "completed", "value": true}]},
            {"id": "broken", "event": "broken", "effects": [
                {"op": "fact", "key": "completed", "value": true},
                {"op": "fail", "message": "synthetic_failure"}]},
            {"id": "cycle", "event": "cycle", "effects": [
                {"op": "emit", "event": {"type": "cycle"}}]}]}

func fresh(definitions: Dictionary) -> RefCounted:
    var world := Kernel.new()
    world.configure(definitions, 0)
    check(world.dispatch_command({"id": "start", "type": "start"}).ok, "timer setup accepted")
    return world

# One game-owned admission/effect/cost boundary shared by live play and its probe.
# The kernel owns guards, inventory, timers, receipts and rollback per dispatch.
# It does not promise an atomic transaction spanning these two dispatch calls.
func step(world: RefCounted, definitions: Dictionary, command: String, index: int) -> Dictionary:
    if not definitions.costs.has(command):
        return {"ok": false, "error": "unknown_cost"}
    var result: Dictionary = world.dispatch_command({"id": "action_%d" % index, "type": command})
    if not result.ok: return result
    if result.get("duplicate", false): return {"ok": false, "error": "duplicate_operation"}
    var cost: Dictionary = world.dispatch({"id": "cost_%d" % index, "type": "advance", "amount": definitions.costs[command]})
    if cost.get("duplicate", false): return {"ok": false, "error": "duplicate_cost"}
    return cost

# Bounded sequence validation, deliberately not search or an impossibility proof.
# Errors/budget/missing prerequisites return unknown with no partial success state.
func probe(definitions: Dictionary, saved: Dictionary, commands: Array, budget: int) -> Dictionary:
    var isolated := Kernel.new()
    isolated.configure(definitions, 0)
    var restored: Dictionary = isolated.restore(saved)
    if not restored.ok: return {"status": "unknown", "reason": restored.error}
    for index in commands.size():
        if index >= budget: return {"status": "unknown", "reason": "budget"}
        var result := step(isolated, definitions, commands[index], index)
        if not result.ok: return {"status": "unknown", "reason": result.error}
    if not isolated.world_fact("completed"):
        return {"status": "unknown", "reason": "no_witness"}
    return {"status": "witness", "snapshot": isolated.snapshot()}

func run() -> void:
    var definitions := policy()
    var live := fresh(definitions)
    var before: Dictionary = live.snapshot()
    var result := probe(definitions, before, ["prepare", "complete"], 2)
    check(result.status == "witness", "prerequisite plus completion yields a real witness")
    check(live.snapshot() == before, "probe preserves every live state field and receipt")
    if result.status == "witness":
        check(result.snapshot.clock == 5 and result.snapshot.facts.completed,
            "effects before time allow commit started before the cutoff")
        check(result.snapshot.facts.closed and not result.snapshot.facts.missed and result.snapshot.timers.is_empty(),
            "actual due timer observes committed completion")
        check(result.snapshot.inventory.part == 0, "authoritative prerequisite acquisition and spending are replayed")
    for failure_case: Dictionary in [
        {"commands": ["complete"], "budget": 2, "reason": "command_unavailable"},
        {"commands": ["prepare", "complete"], "budget": 1, "reason": "budget"},
        {"commands": ["broken"], "budget": 2, "reason": "synthetic_failure"},
        {"commands": ["cycle"], "budget": 2, "reason": "cycle_limit"},
        {"commands": ["prepare"], "budget": 2, "reason": "no_witness"},
        {"commands": ["absent"], "budget": 2, "reason": "unknown_cost"}]:
        var uncertain := probe(definitions, before, failure_case.commands, failure_case.budget)
        check(uncertain.status == "unknown" and uncertain.reason == failure_case.reason,
            "bounded/failed probe stays unknown: " + failure_case.reason)
        check(not uncertain.has("snapshot"), "unknown result never offers partial state as success")
        check(live.snapshot() == before, "failed probe preserves full live snapshot")
    # Accepted saves may already contain an upcoming operation receipt. A fresh
    # query-only namespace would bypass that receipt and invent a transition.
    for receipt: String in ["action_0", "cost_0"]:
        var replayed := before.duplicate(true)
        replayed.processed[receipt] = true
        var held := Kernel.new()
        held.configure(definitions, 0)
        check(held.restore(replayed).ok, "existing receipt is a valid saved state")
        var held_before: Dictionary = held.snapshot()
        var replay_probe := probe(definitions, held_before, ["prepare", "complete"], 2)
        check(replay_probe.status == "unknown" and replay_probe.reason.begins_with("duplicate_"),
            "ok duplicate is not a required transition: " + receipt)
        check(held.snapshot() == held_before, "forecast preserves existing receipt")
        # Explicit negative control only: erasing a receipt is NOT a valid probe.
        var wrong_ids := held_before.duplicate(true)
        wrong_ids.processed.erase(receipt)
        check(probe(definitions, wrong_ids, ["prepare", "complete"], 2).status == "witness",
            "negative control shows fresh identities could invent reachability")
    var malformed := before.duplicate(true)
    malformed.schema = 99
    check(probe(definitions, malformed, ["prepare", "complete"], 2).status == "unknown", "restore error stays unknown")
    check(before == live.snapshot(), "cancelling an advisory query consumes no receipt or time")
    for index in 2:
        check(step(live, definitions, ["prepare", "complete"][index], index).ok, "continue uses the same real boundary")
    check(live.snapshot() == result.get("snapshot", {}), "continued live execution exactly matches the isolated witness")
    var reversed := fresh(definitions)
    check(step(reversed, definitions, "prepare", 0).ok, "ordering control prerequisite accepted")
    check(reversed.dispatch({"id": "wrong_cost", "type": "advance", "amount": 3}).ok, "ordering control reaches cutoff")
    check(not reversed.dispatch_command({"id": "wrong_commit", "type": "complete"}).ok,
        "negative control: time-first ordering really changes admission")
    check(reversed.world_fact("missed"), "negative control runs the actual deadline consequence")
    await check_rendered_recaps()
    print("Consequence contracts: %d/%d checks passed" % [checks - failures.size(), checks])
    quit(0 if failures.is_empty() else 1)

func check_rendered_recaps() -> void:
    # Reuse the actual sample presentation method; asserting model text alone
    # would miss an unused recap string, skipped Label assignment or stale view.
    var view: Control = load("res://main.tscn").instantiate()
    root.add_child(view)
    await process_frame
    var definitions: Dictionary = view._content.world.duplicate(true)
    definitions.initial_facts.merge({"primary_completed": false,
        "secondary_checked": false, "secondary_shared": false})
    Bridge.release_dialogue_resource(view._dialogue)
    view._dialogue = load("res://tests/runtime/consequence_recap.dialogue")
    check(view._dialogue != null, "synthetic recap uses real imported Dialogue Manager resource")
    var branches: Array = []
    for primary: bool in [false, true]:
        for secondary: int in range(3):
            branches.append({"id": "p%d_s%d" % [int(primary), secondary], "when": [
                {"op": "fact_eq", "key": "primary_completed", "value": primary},
                {"op": "fact_eq", "key": "secondary_checked", "value": secondary > 0},
                {"op": "fact_eq", "key": "secondary_shared", "value": secondary == 2}]})
    view._content = {"content_id": "synthetic_outcome", "world": definitions,
        "dialogues": [{"id": "recap", "branches": branches, "fallback": {"id": "unknown"}}]}
    for primary: bool in [false, true]:
        for secondary: int in range(3):
            view._world.configure(definitions, 0)
            var saved: Dictionary = view._world.snapshot()
            saved.facts.primary_completed = primary
            saved.facts.secondary_checked = secondary > 0
            saved.facts.secondary_shared = secondary == 2
            check(view._world.restore(saved).ok, "recap fact combination restored")
            view._bridge.configure(view._world, view._content)
            check(view._bridge.begin_dialogue("recap").ok, "recap session admitted")
            view._body.text = "stale previous outcome"
            await view._show_line("recap")
            await process_frame
            var primary_text := "Primary task completed." if primary else "Primary task incomplete."
            var secondary_text: String = ["Secondary result unchecked.", "Secondary result checked but not shared.", "Secondary result checked and shared."][secondary]
            check(view._body.is_inside_tree() and view._body.is_visible_in_tree(), "recap Label is attached and visible")
            check(view._body.text == "Outcome: " + primary_text + " " + secondary_text,
                "actual rendered Label matches both independent outcomes p%d_s%d" % [int(primary), secondary])
            check(view._world.snapshot() == saved, "rendering does not rewrite facts to match the recap")
    view.free()
