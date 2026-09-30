extends Control
const Kernel = preload("res://addons/story_foundation/runtime/rule_kernel.gd")
const Bridge = preload("res://addons/story_foundation/adapters/dialogue_manager_bridge.gd")
var _world: RefCounted = Kernel.new()
var _bridge: RefCounted = Bridge.new()
var _content: Dictionary = {}
var _dialogue: Resource
var _body: Label
var _status: Label
var _state: Label
var _choices: VBoxContainer
var _busy: bool = false
var _command_counter: int = 0

func _ready() -> void:
	_content = JSON.parse_string(FileAccess.get_file_as_string("res://content/content.json"))
	_dialogue = load("res://content/presentation.dialogue")
	_build_ui()
	_reset()

func _build_ui() -> void:
	var margin := MarginContainer.new()
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	for side: String in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 32)
	add_child(margin)
	var stack := VBoxContainer.new()
	stack.add_theme_constant_override("separation", 18)
	margin.add_child(stack)
	var title := Label.new()
	title.text = "NEWS AT THE VILLAGE SIGNPOST"
	title.add_theme_font_size_override("font_size", 28)
	stack.add_child(title)
	var intro := Label.new()
	intro.text = "A tiny playable story · Godot Story Foundation + Dialogue Manager\nObserve the bridge, talk to Mira, then choose how to help."
	intro.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	stack.add_child(intro)
	var buttons := HBoxContainer.new()
	buttons.add_theme_constant_override("separation", 10)
	stack.add_child(buttons)
	_add_button(buttons, "1. Inspect bridge", _inspect)
	_add_button(buttons, "2. Talk to Mira", _talk)
	_add_button(buttons, "Save", _save)
	_add_button(buttons, "Load", _load_save)
	_add_button(buttons, "Restart", _reset)
	_body = Label.new()
	_body.custom_minimum_size.y = 110
	_body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_body.add_theme_font_size_override("font_size", 24)
	stack.add_child(_body)
	_choices = VBoxContainer.new()
	_choices.add_theme_constant_override("separation", 10)
	stack.add_child(_choices)
	_status = Label.new()
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_status.modulate = Color(0.55, 0.85, 0.75)
	stack.add_child(_status)
	_state = Label.new()
	_state.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_state.add_theme_font_size_override("font_size", 17)
	stack.add_child(_state)
	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	stack.add_child(spacer)
	var note := Label.new()
	note.text = "Public synthetic review fixture. No model or network calls at runtime.\nWorld truth and NPC knowledge are separate. Choices submit guarded commands."
	note.modulate = Color(0.65, 0.70, 0.77)
	stack.add_child(note)

func _add_button(parent: Node, text: String, callback: Callable) -> void:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size.y = 42
	button.pressed.connect(callback)
	parent.add_child(button)

func _clear_choices() -> void:
	for child: Node in _choices.get_children():
		_choices.remove_child(child)
		child.queue_free()

func _reset() -> void:
	if _busy: return
	_world.configure(_content.world, _content.world.actors.size())
	_bridge.configure(_world, _content)
	_body.text = "Mira waits beside the village signpost."
	_status.text = "Talk first if you want to see what Mira knows before you share the news."
	_clear_choices()
	_render_state()

func _inspect() -> void:
	if _busy: return
	_command_counter += 1
	var result: Dictionary = _world.dispatch_command({"id":"inspect:%d:%d" % [_world.snapshot().next_seq, _command_counter],"type":"inspect_bridge"})
	_status.text = "You saw the closed bridge. Mira has not been told yet." if result.ok else str(result.error)
	_clear_choices()
	_render_state()

func _talk() -> void:
	if _busy: return
	_bridge.begin_dialogue("mira_notice")
	await _show_line("mira_notice")

func _show_line(key: String) -> void:
	if _busy: return
	_busy = true
	_clear_choices()
	var manager: Node = get_node("/root/DialogueManager")
	var line: Variant = await manager.get_next_dialogue_line(_dialogue, key, [_bridge])
	if line == null:
		var result: Dictionary = _bridge.last_result
		if result.get("ok", false):
			_status.text = "Choice applied. Talk to Mira again to hear what changed."
		elif not result.is_empty():
			_status.text = "Choice could not apply: %s. Inspect the bridge or talk again." % result.get("error", "unknown")
		else:
			_status.text = "Conversation complete."
	else:
		_body.text = "%s: %s" % [line.character.capitalize(), line.text]
		for response: Variant in line.responses:
			if response.is_allowed:
				_add_button(_choices, response.text, _show_line.bind(response.next_id))
		if line.responses.is_empty() and not str(line.next_id).is_empty():
			_add_button(_choices, "Finish conversation", _show_line.bind(line.next_id))
		_status.text = "Select a response. World guards are checked again when the command runs."
	_render_state()
	_busy = false

func _render_state() -> void:
	var state: Dictionary = _world.snapshot()
	_state.text = "WORLD TRUTH     bridge closed: %s · path marked: %s\nPLAYER KNOWS    bridge closed: %s\nMIRA KNOWS         bridge closed: %s · trust: %d\nINVENTORY          chalk: %d · map: %d · coins: %d" % [str(_world.world_fact("bridge_closed")), str(_world.world_fact("path_marked")), str(_world.npc_knows("player", "bridge_closed", false)), str(_world.npc_knows("mira", "bridge_closed", false)), state.actors.mira.trust, state.inventory.chalk, state.inventory.map, state.coins]

func _save() -> void:
	if _busy: return
	var file := FileAccess.open("user://village.save.json", FileAccess.WRITE)
	if file == null:
		_status.text = "Could not open the save file."
		return
	file.store_string(JSON.stringify(_world.snapshot(), "\t"))
	_status.text = "Saved this world's schema-2 state locally."

func _load_save() -> void:
	if _busy: return
	if not FileAccess.file_exists("user://village.save.json"):
		_status.text = "No saved village yet."
		return
	var value: Variant = JSON.parse_string(FileAccess.get_file_as_string("user://village.save.json"))
	var result: Dictionary = _world.restore(value) if value is Dictionary else {"ok":false,"error":"invalid_json"}
	_status.text = "Restored world, knowledge, inventory and command ledger." if result.ok else "Load rejected: " + str(result.error)
	if result.ok:
		_bridge.configure(_world, _content)
		_clear_choices()
		_body.text = "Village restored. Talk to Mira to continue."
	_render_state()

func _exit_tree() -> void:
	Bridge.release_dialogue_resource(_dialogue)
