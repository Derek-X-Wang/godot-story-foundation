extends SceneTree
## Executes the real pinned Dialogue Manager parser and mutation interpreter.
const Kernel = preload("res://addons/story_foundation/runtime/rule_kernel.gd")
const Bridge = preload("res://addons/story_foundation/adapters/dialogue_manager_bridge.gd")
var _checks: int = 0
var _failed: int = 0
var _world: RefCounted
var _bridge: RefCounted
var _content: Dictionary
var _dialogue: Resource
var _manager: Node

func _initialize() -> void:
	call_deferred("run")

func check(label: String, passed: bool) -> void:
	_checks += 1
	if not passed:
		_failed += 1
		printerr("FAIL: ", label)

func fresh() -> void:
	_world = Kernel.new()
	_world.configure(_content.world, _content.world.actors.size())
	_bridge = Bridge.new()
	_bridge.configure(_world, _content)

func line() -> Variant:
	_bridge.begin_dialogue("mira_notice")
	return await _manager.get_next_dialogue_line(_dialogue, "mira_notice", [_bridge])

func run() -> void:
	_content = JSON.parse_string(FileAccess.get_file_as_string("res://content/content.json"))
	_dialogue = load("res://content/presentation.dialogue")
	_manager = root.get_node("DialogueManager")
	check("actual official Dialogue Manager resource imported", _dialogue != null and _dialogue.get_script().resource_path.ends_with("addons/dialogue_manager/dialogue_resource.gd"))
	fresh()
	check("world truth is separate from NPC knowledge", _bridge.world_fact("bridge_closed") == true and _bridge.npc_knows("mira", "bridge_closed") == null)
	check("choice requires a dialogue session", _bridge.choose("mira_notice", "ignorant", "share_bridge_news").error == "dialogue_not_started")
	check("unknown dialogue rejected", not _bridge.begin_dialogue("unknown").ok)
	var current: Variant = await line()
	check("real DM shows ignorant fallback despite true world fact", current.text.begins_with("I have no news"))
	check("real DM returns approved response", current.responses.size() == 1 and current.responses[0].text == "Share what you saw at the bridge.")
	var before: Dictionary = _world.snapshot()
	var ending: Variant = await _manager.get_next_dialogue_line(_dialogue, current.responses[0].next_id, [_bridge])
	check("unavailable guarded choice ends safely", ending == null and _bridge.last_result.error == "command_unavailable")
	check("unavailable choice does not mutate world", _world.snapshot() == before)
	check("unknown choice rejected", _bridge.choose("mira_notice", "ignorant", "invented").error == "unknown_choice")
	check("cross-dialogue choice rejected", _bridge.choose("other", "ignorant", "share_bridge_news").error == "dialogue_not_started")
	_world.dispatch_command({"id":"inspect_1","type":"inspect_bridge"})
	check("observation teaches player but not Mira", _world.npc_knows("player", "bridge_closed") == true and _world.npc_knows("mira", "bridge_closed") == null)
	current = await line()
	await _manager.get_next_dialogue_line(_dialogue, current.responses[0].next_id, [_bridge])
	check("real DM selection dispatches knowledge and trust effects", _bridge.last_result.ok and _world.npc_knows("mira", "bridge_closed") == true and _world.snapshot().actors.mira.trust == 1)
	before = _world.snapshot()
	var result: Dictionary = _bridge.choose("mira_notice", "ignorant", "share_bridge_news")
	check("same response retry idempotent after branch changes", result.get("duplicate", false) and _world.snapshot() == before)
	current = await line()
	check("real DM selects informed branch", current.text.begins_with("The east bridge is closed. Could") and current.responses.size() == 1)
	await _manager.get_next_dialogue_line(_dialogue, current.responses[0].next_id, [_bridge])
	check("real DM choice uses authoritative inventory effects", _world.snapshot().inventory.chalk == 0 and _world.snapshot().inventory.map == 1)
	check("real DM choice applies one-time reward", _world.snapshot().coins == 5 and _world.world_fact("path_marked") == true)
	before = _world.snapshot()
	_bridge.choose("mira_notice", "informed", "mark_safe_path")
	check("path response retry cannot double spend or reward", _world.snapshot() == before)
	current = await line()
	check("completed first-match branch wins over informed branch", current.text.contains("safe path is marked") and current.responses.is_empty())
	check("only first branch reports available", _bridge.branch_available("mira_notice", "path_marked") and not _bridge.branch_available("mira_notice", "informed"))
	var branch: Dictionary = _bridge.selected_branch("mira_notice")
	branch.text = "tampered"
	check("adapter branch query returns a copy", _bridge.selected_branch("mira_notice").text != "tampered")

	fresh()
	_world.dispatch_command({"id":"inspect_stale","type":"inspect_bridge"})
	await line()
	_world.dispatch_command({"id":"external_share","type":"share_news"})
	before = _world.snapshot()
	result = _bridge.choose("mira_notice", "ignorant", "share_bridge_news")
	check("stale visible branch rejected", result.error == "stale_branch" and _world.snapshot() == before)
	var saved: Dictionary = JSON.parse_string(JSON.stringify(_world.snapshot()))
	fresh()
	check("demo save roundtrip restores knowledge", _world.restore(saved).ok and _world.npc_knows("mira", "bridge_closed") == true)
	current = await line()
	await _manager.get_next_dialogue_line(_dialogue, current.responses[0].next_id, [_bridge])
	check("choice after save reload does not collide with old session", _bridge.last_result.ok and not _bridge.last_result.get("duplicate", false) and _world.snapshot().coins == 5)
	# Replay the same declared fixtures that the offline Python simulator reviews.
	var fixtures: Array = JSON.parse_string(FileAccess.get_file_as_string("res://tests/runtime/village_fixtures.json"))
	for fixture: Dictionary in fixtures:
		fresh()
		for step: Dictionary in fixture.steps:
			before = _world.snapshot()
			result = _world.dispatch_command({"id":step.action_id,"type":step.command})
			var outcome: String = "blocked" if not result.ok else ("duplicate" if result.get("duplicate",false) else "applied")
			check("simulation parity " + str(fixture.id) + ":" + str(step.action_id) + ":" + str(step.expect), outcome == step.expect)
			if outcome == "blocked":
				check("blocked fixture command keeps exact state", _world.snapshot() == before)
		for dialogue_id: String in fixture.expect_dialogues:
			check("simulation branch parity " + str(fixture.id), _bridge.branch_available(dialogue_id, fixture.expect_dialogues[dialogue_id]))
		check("simulation state parity " + str(fixture.id), contains_expected(_world.snapshot(), fixture.expect_state))
	Bridge.release_dialogue_resource(_dialogue)
	print("Dialogue Manager integration: %d/%d checks passed" % [_checks - _failed, _checks])
	quit(0 if _failed == 0 else 1)

func contains_expected(actual: Variant, expected: Variant) -> bool:
	if expected is Dictionary:
		if not actual is Dictionary: return false
		for key: String in expected:
			if not actual.has(key) or not contains_expected(actual[key], expected[key]): return false
		return true
	return actual == expected
