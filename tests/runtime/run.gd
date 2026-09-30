# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang

extends SceneTree
const Kernel = preload("res://addons/story_foundation/runtime/rule_kernel.gd")
var kernel: Variant
var story: Dictionary
var checks: Array = []
var fixtures: Dictionary = {}
var counter: int = 0

func _initialize() -> void: call_deferred("run")
func check(label: String, condition: bool, detail: Variant = null) -> void:
	checks.append({"name":label,"passed":condition,"detail":detail})
	if not condition: printerr("FAIL: ",label," ",detail)
func act(kind: String, extra: Dictionary = {}, id: String = "") -> Dictionary:
	counter += 1
	var action: Dictionary = extra.duplicate(true)
	action.type = kind
	action.id = id if not id.is_empty() else "test_%05d" % counter
	var result: Dictionary = kernel.dispatch(action)
	return result
func fresh(custom: Dictionary = {}) -> void:
	kernel.configure(story if custom.is_empty() else custom,12)
func state() -> Dictionary: return kernel.snapshot()
func fixture(label: String) -> void:
	var value: Dictionary = state()
	value.erase("trace")
	fixtures[label] = value
func add_rule(data: Dictionary,id: String,event: String,effects: Array,priority: int=0,when: Array=[]) -> void:
	data.rules.append({"id":id,"event":event,"effects":effects,"priority":priority,"when":when})

func run() -> void:
	story = JSON.parse_string(FileAccess.get_file_as_string("res://tests/runtime/story.json"))
	kernel = Kernel.new()
	fresh()
	check("fresh world 12 actors",state().actors.size()==12)
	act("travel",{"scene":"clinic"})
	check("conditional clinic entrance blocks without invitation",state().scene=="village")
	act("promise")
	act("travel",{"scene":"forest"})
	act("gather")
	act("travel",{"scene":"village"})
	act("brew")
	act("travel",{"scene":"clinic"})
	act("deliver",{},"deliver_once")
	check("honest branch completes with idempotent reward",state().facts.get("healed",false) and state().coins==10 and state().actors.patient.trust==2)
	var before: Dictionary = state()
	var duplicate: Dictionary = act("deliver",{},"deliver_once")
	check("same action retry is exact no-op",duplicate.get("duplicate",false) and state()==before)
	act("delivered")
	check("reward deduplicated across distinct action IDs",state().coins==10)
	act("tell_guard")
	act("talk_guard")
	act("travel",{"scene":"storehouse"})
	check("knowledge and trust unlock conditional door",state().scene=="storehouse")
	act("advance",{"amount":6})
	check("timed condition reevaluates after healing",not state().facts.has("worsened") and state().timers.is_empty())
	fixture("honest")
	var saved: Dictionary = JSON.parse_string(JSON.stringify(state()))
	fresh()
	check("save/load exact semantic roundtrip",kernel.restore(saved).ok and JSON.parse_string(JSON.stringify(state()))==JSON.parse_string(JSON.stringify(saved)))
	check("idempotency ledger survives save/load",act("deliver",{},"deliver_once").get("duplicate",false))

	fresh()
	act("take_medicine")
	check("witness knows fact but guard does not",state().facts.stolen and state().actors.witness.knowledge.stolen and not state().actors.guard.knowledge.has("stolen"))
	act("talk_guard")
	check("unknown truth cannot trigger NPC dialogue",state().actors.guard.trust==0)
	act("discover",{"npc":"guard","fact":"stolen"})
	act("talk_guard")
	check("discovery changes guard memory independently",state().actors.guard.trust==-2 and state().actors.guard.memory.has("dialogue"))
	fixture("theft")

	fresh()
	act("promise")
	saved = state()
	fresh()
	kernel.restore(saved)
	act("advance",{"amount":6})
	check("pending timer restored and fires once",state().facts.get("worsened",false) and state().actors.healer.trust==-1 and state().timers.is_empty())
	act("advance",{"amount":1})
	check("timer cannot double-fire",state().actors.healer.trust==-1)
	fixture("deadline")

	fresh()
	saved = state()
	saved.queue = [{"type":"deadline","seq":20}]
	saved.next_seq = 21
	kernel.restore(saved)
	var result: Dictionary = act("promise")
	check("restored queue executes before submitted action",result.ok and state().facts.worsened and state().actors.healer.memory.promise=="medicine before dusk")
	check("pending queue drained without dropped consequence",state().queue.is_empty() and result.events_processed==2)
	fixture("pending_queue")

	var custom: Dictionary = story.duplicate(true)
	add_rule(custom,"a_first","conflict",[{"op":"fact","key":"conflict","value":1},{"op":"emit","event":{"type":"child"}}])
	add_rule(custom,"z_last","conflict",[{"op":"fact","key":"conflict","value":2}])
	add_rule(custom,"child_rule","child",[{"op":"fact","key":"child_saw_final","value":true}],0,[{"op":"fact_eq","key":"conflict","value":2}])
	fresh(custom)
	result = act("conflict")
	check("ordered conflicts and emitted FIFO semantics",result.ok and state().facts.conflict==2 and state().facts.child_saw_final)
	fixture("conflict")

	custom = story.duplicate(true)
	add_rule(custom,"poison","poison",[{"op":"fact","key":"partial","value":true},{"op":"trust","npc":"guard","delta":9},{"op":"reward","key":"bad_reward","coins":99},{"op":"emit","event":{"type":"deadline"}},{"op":"fail","message":"injected_failure"}],0,[{"op":"fact_eq","key":"allow_poison","value":null}])
	fresh(custom)
	before = state()
	result = act("poison",{},"retry_me")
	check("mid-action failure rolls back all state",not result.ok and result.error=="injected_failure" and state()==before)
	saved = state()
	saved.facts.allow_poison = true
	kernel.restore(saved)
	result = act("poison",{},"retry_me")
	check("failed action ID can be retried",result.ok and not result.duplicate)

	custom = story.duplicate(true)
	add_rule(custom,"cycle","loop",[{"op":"fact","key":"cycle_write","value":true},{"op":"emit","event":{"type":"loop"}}])
	fresh(custom)
	before = state()
	result = act("loop",{},"cycle_id")
	check("bounded cycle diagnosed and complete rollback",not result.ok and result.error=="cycle_limit" and state()==before and result.trace.size()>64)
	saved = state()
	saved.queue = [{"type":"loop","seq":30}]
	saved.next_seq = 31
	kernel.restore(saved)
	before = state()
	result = act("greet",{"npc":"guard"})
	check("failed restored queue remains pending, not silently lost",not result.ok and state()==before and state().queue.size()==1)

	fresh()
	before = state()
	result = act("greet",{"npc":"nonexistent"})
	check("unknown actor rejects atomically",not result.ok and state()==before)
	check("invalid negative clock step rejects atomically",not act("advance",{"amount":-1}).ok and state()==before)
	check("invalid empty ID rejected",not kernel.dispatch({"id":"","type":"gather"}).ok and state()==before)

	fresh()
	saved = state()
	saved.schema = 1
	saved.time = 4
	saved.erase("clock")
	for actor: Dictionary in saved.actors.values():
		actor.erase("knowledge")
		actor.erase("memory")
	saved.actors.guard.trust = 3
	result = kernel.restore(saved)
	check("v1 migration preserves trust and introduces knowledge",result.ok and result.migrated and state().clock==4 and state().actors.guard.trust==3 and state().actors.guard.knowledge=={})
	fixture("migration")
	before = state()
	saved = state()
	saved.schema = 99
	check("future schema rejected without mutation",not kernel.restore(saved).ok and state()==before)
	saved = state()
	saved.content_version = 99
	check("future content version rejected without mutation",not kernel.restore(saved).ok and state()==before)
	saved = state()
	saved.actors.guard.knowledge = "bad"
	check("malformed save rejected without mutation",not kernel.restore(saved).ok and state()==before)

	# Held-out composition: unwitnessed theft, late healing, later independent discovery,
	# conflicting gratitude/theft rules. No dedicated held-out path exists in content.
	fresh()
	saved = state()
	saved.facts.witness_present = false
	kernel.restore(saved)
	act("promise")
	act("take_medicine")
	act("advance",{"amount":6})
	act("travel",{"scene":"clinic"})
	act("deliver")
	act("discover",{"npc":"merchant","fact":"stolen"})
	act("tell_guard")
	act("discover",{"npc":"guard","fact":"stolen"})
	act("talk_guard")
	act("travel",{"scene":"storehouse"})
	check("held-out combination reuses generic rules",state().facts.healed and state().facts.worsened and state().coins==10 and state().scene=="clinic" and state().facts.gate_open==false and state().actors.merchant.knowledge.stolen and not state().actors.witness.knowledge.has("stolen"))
	fixture("held_out")

	custom = story.duplicate(true)
	custom.actors.append("ranger")
	add_rule(custom,"ranger_thanks","meet_ranger",[{"op":"trust","npc":"ranger","delta":2},{"op":"remember","npc":"ranger","key":"thanks","value":"The forest remembers kindness."},{"op":"reward","key":"ranger_thanks","coins":3}],0,[{"op":"fact_eq","key":"healed","value":true}])
	fresh(custom)
	saved = state()
	saved.facts.healed = true
	kernel.restore(saved)
	act("meet_ranger")
	act("meet_ranger")
	check("authoring exercise same new NPC/rule/consequence",state().actors.ranger.trust==4 and state().coins==3 and state().actors.ranger.memory.has("thanks"))
	fixture("authoring")
	# Exercise the actual presentation type and its signal lifetime, not an empty node.
	before = state()
	for i: int in range(5):
		var view = load("res://tests/runtime/world_view_fixture.gd").new()
		root.add_child(view)
		view.set_world(state())
		view.landmark_clicked.connect(func(_label:String): act("greet",{"npc":"ranger"}))
		view.free()
	check("actual world view unload/re-entry preserves authority",state()==before)
	var active_view = load("res://tests/runtime/world_view_fixture.gd").new()
	root.add_child(active_view)
	active_view.set_world(state())
	active_view.landmark_clicked.connect(func(_label:String): act("greet",{"npc":"ranger"}))
	active_view.landmark_clicked.emit("RANGER")
	check("actual view signal after re-entry causes exactly one mutation",state().actors.ranger.trust==5)
	active_view.free()

	for malformed: String in ["fraction_schema","text_schema","queue_seq","negative_timer","bad_ledger","bad_trace","fraction_fact"]:
		fresh()
		before = state()
		saved = state()
		match malformed:
			"fraction_schema": saved.schema = 2.5
			"text_schema": saved.schema = "future"
			"queue_seq": saved.queue = [{"type":"deadline","seq":0}]
			"negative_timer": saved.timers = [{"due":-1,"seq":0,"event":{"type":"deadline"}}]
			"bad_ledger": saved.processed.x = "bad"
			"bad_trace": saved.trace = [9]
			"fraction_fact": saved.facts.number = 0.5
		result = kernel.restore(saved)
		check("malformed save atomic rejection: "+malformed,not result.ok and state()==before)
	for invalid_condition: Dictionary in [{"op":"unknown","value":true},{"op":"trust_gte","npc":"absent","value":1},{"op":"inventory_gte","key":"absent","value":1}]:
		custom = story.duplicate(true)
		add_rule(custom,"invalid_condition","invalid_condition",[{"op":"fact","key":"unreachable","value":true}],0,[invalid_condition])
		fresh(custom)
		before = state()
		result = act("invalid_condition")
		check("invalid rule condition aborts: "+str(invalid_condition.op),not result.ok and state()==before)
	custom = story.duplicate(true)
	add_rule(custom,"parameterized","parameterized",[{"op":"trust","npc":"$npc","delta":"$delta"}])
	fresh(custom)
	result = act("parameterized",{"npc":"guard","delta":3})
	check("event-supplied numeric effect resolves",result.ok and state().actors.guard.trust==3)

	custom = story.duplicate(true)
	fresh(custom)
	custom.rules[0].effects[0].value = false
	act("promise")
	check("configured content isolated from caller mutation",state().facts.promised==true)
	for effect_op: String in ["emit","timer"]:
		custom = story.duplicate(true)
		add_rule(custom,"empty_event","empty_event",[{"op":effect_op,"delay":1,"event":{"type":""}}])
		fresh(custom)
		before = state()
		result = act("empty_event")
		check("empty "+effect_op+" event rejects atomically",not result.ok and state()==before)

	check("original regression check count", checks.size() == 46)
	run_portable_api_checks()
	run_command_checks()
	run_save_contract_checks()
	run_queued_command_checks()

	var passed: int = 0
	for item: Dictionary in checks:
		if item.passed: passed += 1
	var output: Dictionary = {"suite":"runtime","passed":passed,"total":checks.size(),"checks":checks,"fixtures":fixtures}
	var file := FileAccess.open("user://runtime_test_results.json",FileAccess.WRITE)
	file.store_string(JSON.stringify(output,"  "))
	file.close()
	print("TEST_SUMMARY runtime ",passed,"/",checks.size())
	kernel.shutdown()
	kernel = null
	quit(0 if passed==checks.size() else 1)


func run_portable_api_checks() -> void:
	var custom: Dictionary = {
		"version": 7,
		"actors": ["archivist"],
		"initial_scene": "observatory",
		"initial_inventory": {"crystal": 2, "map": 0},
		"initial_facts": {"route": {"stops": ["observatory"]}},
		"rules": []
	}
	add_rule(custom, "exchange", "exchange", [
		{"op": "inventory", "key": "crystal", "delta": -1},
		{"op": "inventory", "key": "map", "delta": 1},
		{"op": "know", "npc": "archivist", "key": "route", "value": {"stops": ["library"]}}
	], 0, [{"op": "inventory_gte", "key": "crystal", "value": 1}])
	add_rule(custom, "record_payload", "record_payload", [
		{"op": "fact", "key": "payload", "value": "$payload"},
		{"op": "know", "npc": "archivist", "key": "payload", "value": "$payload"}
	])
	kernel.configure(custom, 0)
	check("generic content sets scene inventory and version", state().scene == "observatory" and state().inventory == {"crystal": 2, "map": 0} and state().content_version == 7)
	check("zero padding keeps authored actor population", state().actors.keys() == ["archivist"])
	custom.initial_inventory.crystal = 99
	custom.initial_facts.route.stops.append("caller mutation")
	check("initial inventory and facts are copied", state().inventory.crystal == 2 and kernel.world_fact("route").stops == ["observatory"])
	var result: Dictionary = act("exchange")
	check("generic inventory effects apply transactionally", result.ok and state().inventory == {"crystal": 1, "map": 1})
	var saved: Dictionary = JSON.parse_string(JSON.stringify(state()))
	check("generic inventory schema2 roundtrip", kernel.restore(saved).ok and JSON.parse_string(JSON.stringify(state())) == saved)
	var before: Dictionary = state()
	saved.inventory.erase("crystal")
	check("save missing declared item rejects atomically", not kernel.restore(saved).ok and state() == before)
	saved = state()
	saved.inventory.crystal = -1
	check("negative generic inventory rejects atomically", not kernel.restore(saved).ok and state() == before)
	saved = state()
	saved.content_version = "bad"
	check("malformed content version rejects atomically", not kernel.restore(saved).ok and state() == before)

	var fact: Dictionary = kernel.world_fact("route")
	fact.stops.append("mutated fact")
	check("world fact returns a deep copy", state() == before and kernel.world_fact("route").stops == ["observatory"])
	var knowledge: Dictionary = kernel.npc_knows("archivist", "route")
	knowledge.stops.append("mutated knowledge")
	check("NPC knowledge returns a deep copy", state() == before and kernel.npc_knows("archivist", "route").stops == ["library"])
	check("NPC query does not leak world facts", kernel.npc_knows("archivist", "missing") == null and kernel.npc_knows("unknown", "route") == null)
	var fallback: Dictionary = {"choices": ["fallback"]}
	var fallback_fact: Dictionary = kernel.world_fact("missing", fallback)
	var fallback_knowledge: Dictionary = kernel.npc_knows("unknown", "missing", fallback)
	fallback_fact.choices.append("fact mutation")
	fallback_knowledge.choices.append("knowledge mutation")
	check("query fallback values are copied", fallback.choices == ["fallback"] and state() == before)
	var exported: Dictionary = state()
	exported.facts.route.stops.append("snapshot fact mutation")
	exported.actors.archivist.knowledge.route.stops.append("snapshot knowledge mutation")
	exported.inventory.crystal = 100
	check("snapshot deeply isolates every authority store", state() == before)

	var event: Dictionary = {"npc": "archivist", "item": "crystal", "amount": 1, "route": {"stops": ["library"]}}
	var event_before: Dictionary = event.duplicate(true)
	var conditions: Array = [
		{"op": "fact_eq", "key": "route", "value": {"stops": ["observatory"]}},
		{"op": "inventory_gte", "key": "$item", "value": "$amount"},
		{"op": "trust_gte", "npc": "$npc", "value": 0},
		{"op": "knows", "npc": "$npc", "key": "route", "value": "$route"},
		{"op": "event_eq", "key": "amount", "value": 1},
		{"op": "scene_eq", "value": "observatory"}
	]
	var conditions_before: Array = conditions.duplicate(true)
	result = kernel.evaluate_conditions(conditions, event)
	check("read query evaluates complete condition language", result == {"ok": true, "matched": true, "error": ""})
	check("condition query leaves world and arguments unchanged", state() == before and event == event_before and conditions == conditions_before)
	result = kernel.evaluate_conditions([{"op": "scene_eq", "value": "other"}])
	check("unmatched condition is not an error", result == {"ok": true, "matched": false, "error": ""} and state() == before)
	check("empty condition list matches", kernel.evaluate_conditions([]) == {"ok": true, "matched": true, "error": ""})
	var bad_conditions: Array = [
		{"conditions": [{"op": "unknown"}], "error": "unknown_condition:unknown"},
		{"conditions": [{"op": "knows", "npc": "absent"}], "error": "unknown_actor:absent"},
		{"conditions": [{"op": "trust_gte", "npc": "archivist", "value": 0.5}], "error": "invalid_integer"},
		{"conditions": [{"op": "inventory_gte", "key": "crystal", "value": "one"}], "error": "invalid_integer"},
		{"conditions": [{"op": "inventory_gte", "key": "absent", "value": 1}], "error": "unknown_item:absent"},
		{"conditions": ["not a condition"], "error": "invalid_condition"},
		{"conditions": [{}], "error": "invalid_condition"},
		{"conditions": {}, "error": "invalid_conditions"}
	]
	for invalid: Dictionary in bad_conditions:
		result = kernel.evaluate_conditions(invalid.conditions)
		check("read condition error: " + invalid.error, result == {"ok": false, "matched": false, "error": invalid.error} and state() == before)
	check("condition error does not poison later evaluations", kernel.evaluate_conditions([]).ok)

	var action: Dictionary = {"id": "copied_action", "type": "record_payload", "payload": {"steps": [1, 2]}}
	result = kernel.dispatch(action)
	before = state()
	action.payload.steps.append(3)
	result.trace.append("mutated result")
	check("action and dispatch result cannot mutate authority", state() == before and kernel.world_fact("payload").steps == [1, 2])
	saved = state()
	result = kernel.restore(saved)
	before = state()
	saved.actors.archivist.knowledge.payload.steps.append(4)
	saved.facts.payload.steps.append(5)
	check("restore copies caller-owned save data", result.ok and state() == before)

	saved = state()
	saved.schema = 1
	saved.time = 8
	saved.erase("clock")
	saved.erase("scene")
	saved.erase("inventory")
	result = kernel.restore(saved)
	check("legacy migration uses declared scene and inventory", result.ok and result.migrated and state().scene == "observatory" and state().inventory == {"crystal": 2, "map": 0} and state().clock == 8 and state().content_version == 7)

	kernel.configure({"version": 1, "actors": [], "rules": [], "initial_inventory": {}}, 0)
	check("explicit empty inventory has no legacy items", state().inventory.is_empty() and kernel.restore(state()).ok)
	fresh()
	check("undeclared inventory and scene retain legacy defaults", state().scene == "village" and state().inventory == {"herb": 0, "medicine": 0})
	var exposed: bool = false
	for property: Dictionary in kernel.get_property_list():
		if property.name in ["state", "content"]:
			exposed = true
	check("runtime exposes no public state or content property", not exposed)


func run_command_checks() -> void:
	var custom: Dictionary = {
		"version": 1, "actors": [], "rules": [], "initial_inventory": {}
	}
	add_rule(custom, "observe", "observe", [{"op": "fact", "key": "seen", "value": true}])
	add_rule(custom, "share", "share", [{"op": "fact", "key": "shared", "value": true}], 0, [
		{"op": "fact_eq", "key": "seen", "value": true},
		{"op": "fact_eq", "key": "shared", "value": null}
	])
	kernel.configure(custom, 0)
	var before: Dictionary = state()
	var command: Dictionary = {"id": "share_retry", "type": "share"}
	var result: Dictionary = kernel.dispatch_command(command)
	check("unavailable gameplay command leaves exact state and ID unused", result == {"ok": false, "error": "command_unavailable", "trace": []} and state() == before)
	result = kernel.dispatch_command({"id": "observe_once", "type": "observe"})
	check("available gameplay command dispatches", result.ok and kernel.world_fact("seen", false))
	result = kernel.dispatch_command(command)
	check("blocked command ID succeeds after conditions change", result.ok and not result.duplicate and kernel.world_fact("shared", false) and state().processed.has("share_retry"))
	before = state()
	result = kernel.dispatch_command(command)
	check("command duplicate survives now-unavailable guard", result == {"ok": true, "duplicate": true, "events_processed": 0, "trace": []} and state() == before)
	result = kernel.dispatch_command({"id": "share_retry", "type": "unknown_type"})
	check("known command ID is duplicate before command lookup", result.get("duplicate", false) and state() == before)
	result = kernel.dispatch_command({"id": "unknown_once", "type": "unknown_type"})
	check("unknown gameplay command leaves exact state", result == {"ok": false, "error": "unknown_command", "trace": []} and state() == before)
	result = kernel.dispatch_command({"id": "", "type": "observe"})
	check("invalid gameplay command leaves exact state", result == {"ok": false, "error": "invalid_action", "trace": []} and state() == before)
	result = kernel.dispatch({"id": "raw_unknown", "type": "unknown_type"})
	check("raw dispatch still accepts unhandled events", result.ok and state().processed.has("raw_unknown") and state().facts == before.facts)
	result = kernel.dispatch({"id": "raw_unavailable", "type": "share"})
	check("raw dispatch still accepts unmatched registered events", result.ok and state().processed.has("raw_unavailable") and state().facts == before.facts)

	add_rule(custom, "invalid_guard", "invalid_guard", [], 0, [{"op": "unknown"}])
	kernel.configure(custom, 0)
	before = state()
	result = kernel.dispatch_command({"id": "invalid_guard_once", "type": "invalid_guard"})
	check("gameplay command condition errors propagate atomically", not result.ok and result.error == "unknown_condition:unknown" and state() == before)

	add_rule(custom, "first_choice", "choose", [], 0, [{"op": "fact_eq", "key": "unmet", "value": true}])
	add_rule(custom, "second_choice", "choose", [{"op": "fact", "key": "chosen", "value": true}], 1)
	kernel.configure(custom, 0)
	result = kernel.dispatch_command({"id": "choose_once", "type": "choose"})
	check("gameplay command accepts any matching rule", result.ok and kernel.world_fact("chosen", false))

	add_rule(custom, "write_first", "revalidate", [{"op": "fact", "key": "partial", "value": true}], 0)
	add_rule(custom, "invalid_later", "revalidate", [], 1, [{"op": "unknown"}])
	kernel.configure(custom, 0)
	before = state()
	result = kernel.dispatch_command({"id": "revalidate_once", "type": "revalidate"})
	check("accepted command revalidates and rolls back transaction errors", not result.ok and result.error == "unknown_condition:unknown" and state() == before)


func run_save_contract_checks() -> void:
	const MAX_SAFE: int = 9007199254740991
	var custom: Dictionary = {
		"version": 1,
		"actors": ["keeper"],
		"initial_facts": {"bridge_closed": true, "count": 0, "label": "bridge", "nullable": null},
		"initial_inventory": {"token": 1},
		"rules": []
	}
	add_rule(custom, "set_count", "set_count", [{"op": "fact", "key": "count", "value": "$value"}])
	add_rule(custom, "set_dynamic", "set_dynamic", [{"op": "fact", "key": "dynamic", "value": "$value"}])
	add_rule(custom, "add_token", "add_token", [{"op": "inventory", "key": "token", "delta": "$delta"}])
	add_rule(custom, "add_trust", "add_trust", [{"op": "trust", "npc": "keeper", "delta": "$delta"}])
	add_rule(custom, "add_coins", "add_coins", [{"op": "reward", "key": "test_reward", "coins": "$delta"}])
	add_rule(custom, "set_timer", "set_timer", [{"op": "timer", "delay": "$delay", "event": {"type": "tick"}}])
	add_rule(custom, "temporary_overflow", "temporary_overflow", [
		{"op": "inventory", "key": "token", "delta": 1},
		{"op": "inventory", "key": "token", "delta": -1}
	])
	kernel.configure(custom, 0)
	var base: Dictionary = state()
	var saved: Dictionary = state()
	saved.facts.erase("bridge_closed")
	var result: Dictionary = kernel.restore(saved)
	check("save missing declared fact rejects without mutation", not result.ok and result.error == "invalid_save:missing_fact" and state() == base)
	for pair: Array in [["bridge_closed", "false"], ["bridge_closed", 1], ["count", "one"], ["label", 1], ["nullable", "value"]]:
		saved = base.duplicate(true)
		saved.facts[pair[0]] = pair[1]
		result = kernel.restore(saved)
		check("save preserves declared fact type: " + str(pair), not result.ok and result.error == "invalid_save:fact_type" and state() == base)
	saved = base.duplicate(true)
	saved.facts.count = 2.0
	saved.facts.dynamic = {"events": [1, true, "new"]}
	result = kernel.restore(saved)
	check("integral JSON numbers and additional facts remain compatible", result.ok and kernel.world_fact("count") == 2 and kernel.world_fact("dynamic").events.size() == 3)
	var before: Dictionary = state()
	result = act("set_count", {"value": "bad"})
	check("transaction cannot change declared numeric fact to text", not result.ok and result.error == "invalid_fact_type" and state() == before)
	result = act("set_dynamic", {"value": MAX_SAFE + 1})
	check("transaction cannot commit unsafe dynamic fact integer", not result.ok and result.error == "invalid_integer" and state() == before)

	for number: Variant in [MAX_SAFE + 1, -MAX_SAFE - 1, INF, -INF, NAN, 0.5]:
		saved = before.duplicate(true)
		saved.facts.dynamic = number
		result = kernel.restore(saved)
		check("unsafe or fractional save number rejects: " + str(number), not result.ok and state() == before)
	saved = base.duplicate(true)
	saved.facts.count = MAX_SAFE
	saved.facts.dynamic = -MAX_SAFE
	saved.inventory.token = MAX_SAFE
	saved.actors.keeper.trust = -MAX_SAFE
	saved.coins = MAX_SAFE
	result = kernel.restore(JSON.parse_string(JSON.stringify(saved)))
	check("inclusive JSON-safe integer boundaries roundtrip", result.ok and kernel.world_fact("count") == MAX_SAFE and kernel.world_fact("dynamic") == -MAX_SAFE and state().inventory.token == MAX_SAFE and state().actors.keeper.trust == -MAX_SAFE and state().coins == MAX_SAFE)
	before = state()
	result = act("add_token", {"delta": 1})
	check("inventory sum overflow rejects atomically", not result.ok and result.error == "invalid_integer" and state() == before)
	result = act("temporary_overflow")
	check("intermediate overflow rejects even if later compensated", not result.ok and result.error == "invalid_integer" and state() == before)
	result = act("add_trust", {"delta": -1})
	check("negative trust overflow rejects atomically", not result.ok and result.error == "invalid_integer" and state() == before)
	result = act("add_coins", {"delta": 1})
	check("reward sum overflow rejects without reward ledger entry", not result.ok and result.error == "invalid_integer" and state() == before)

	saved = base.duplicate(true)
	saved.clock = MAX_SAFE
	kernel.restore(saved)
	before = state()
	result = act("advance", {"amount": 1})
	check("clock overflow rejects atomically", not result.ok and result.error == "invalid_integer" and state() == before)
	result = act("set_timer", {"delay": 1})
	check("timer due overflow rejects atomically", not result.ok and result.error == "invalid_integer" and state() == before)
	saved = base.duplicate(true)
	saved.next_seq = MAX_SAFE
	kernel.restore(saved)
	before = state()
	result = act("unhandled")
	check("event sequence overflow rejects atomically", not result.ok and result.error == "invalid_integer" and state() == before)
	saved = base.duplicate(true)
	saved.schema = 1
	saved.erase("facts")
	result = kernel.restore(saved)
	check("legacy migration restores missing facts from content defaults", result.ok and result.migrated and state().facts == custom.initial_facts)


func run_queued_command_checks() -> void:
	var custom: Dictionary = {
		"version": 1,
		"actors": [],
		"initial_facts": {"ready": true},
		"initial_inventory": {},
		"rules": []
	}
	add_rule(custom, "enable", "enable", [{"op": "fact", "key": "ready", "value": true}])
	add_rule(custom, "disable", "disable", [{"op": "fact", "key": "ready", "value": false}])
	add_rule(custom, "use", "use", [{"op": "fact", "key": "used", "value": true}], 0, [{"op": "fact_eq", "key": "ready", "value": true}])
	add_rule(custom, "invalid", "invalid", [], 0, [{"op": "unknown"}])
	kernel.configure(custom, 0)
	var saved: Dictionary = state()
	saved.queue = [{"type": "disable", "seq": 10}]
	saved.next_seq = 11
	kernel.restore(saved)
	var before: Dictionary = state()
	var result: Dictionary = kernel.dispatch_command({"id": "use_once", "type": "use"})
	check("pending event invalidating command guard rolls back queue and ID", result == {"ok": false, "error": "command_unavailable", "trace": []} and state() == before and not state().processed.has("use_once"))

	kernel.configure(custom, 0)
	saved = state()
	saved.facts.ready = false
	saved.queue = [{"type": "enable", "seq": 10}]
	saved.next_seq = 11
	kernel.restore(saved)
	result = kernel.dispatch_command({"id": "use_once", "type": "use"})
	check("pending event enabling command guard commits both events", result.ok and result.events_processed == 2 and kernel.world_fact("used", false) and kernel.world_fact("ready", false) and state().processed.has("use_once") and state().queue.is_empty())

	kernel.configure(custom, 0)
	saved = state()
	saved.facts.ready = false
	saved.queue = [{"type": "enable", "seq": 10}]
	saved.next_seq = 11
	kernel.restore(saved)
	before = state()
	result = kernel.dispatch_command({"id": "invalid_once", "type": "invalid"})
	check("submitted condition error rolls back previously processed queue", not result.ok and result.error == "unknown_condition:unknown" and state() == before and not state().processed.has("invalid_once"))
