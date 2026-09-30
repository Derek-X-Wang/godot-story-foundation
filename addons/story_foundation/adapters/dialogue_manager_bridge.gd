extends RefCounted
## Narrow Dialogue Manager state object. Generated dialogue calls only these methods.
## The game owns the world; selections dispatch commands through its transaction API.
var story: RefCounted:
	get: return self
var last_result: Dictionary = {}
var _world: RefCounted
var _content: Dictionary = {}
var _dialogues: Dictionary = {}
var _session_id: String = ""
var _session_dialogue: String = ""
var _session_counter: int = 0
var _submitted: Dictionary = {}

func configure(world: RefCounted, approved_content: Dictionary) -> void:
	_world = world
	_content = approved_content.duplicate(true)
	_dialogues.clear()
	for dialogue: Dictionary in _content.get("dialogues", []):
		_dialogues[str(dialogue.id)] = dialogue
	_session_id = ""
	_session_dialogue = ""
	_submitted.clear()
	last_result = {}

func begin_dialogue(dialogue_id: String) -> Dictionary:
	if not _dialogues.has(dialogue_id):
		return {"ok":false,"error":"unknown_dialogue"}
	_session_counter += 1
	# next_seq is persisted: a resumed game cannot accidentally reuse a previous
	# successful choice ID just because this bridge's local counter restarted.
	_session_id = "%s:%s:%d:%d" % [str(_content.get("content_id", "story")), dialogue_id, int(_world.snapshot().next_seq), _session_counter]
	_session_dialogue = dialogue_id
	_submitted.clear()
	last_result = {}
	return {"ok":true,"session_id":_session_id}

func selected_branch(dialogue_id: String) -> Dictionary:
	if not _dialogues.has(dialogue_id): return {}
	var dialogue: Dictionary = _dialogues[dialogue_id]
	for branch: Dictionary in dialogue.get("branches", []):
		var result: Dictionary = _world.evaluate_conditions(branch.get("when", []))
		if not result.ok: return {}
		if result.matched: return branch.duplicate(true)
	return dialogue.get("fallback", {}).duplicate(true)

func branch_available(dialogue_id: String, branch_id: String) -> bool:
	return str(selected_branch(dialogue_id).get("id", "")) == branch_id

func world_fact(key: String, default_value: Variant = null) -> Variant:
	return _world.world_fact(key, default_value)

func npc_knows(npc: String, key: String, default_value: Variant = null) -> Variant:
	return _world.npc_knows(npc, key, default_value)

func choose(dialogue_id: String, branch_id: String, choice_id: String) -> Dictionary:
	if _session_id.is_empty() or dialogue_id != _session_dialogue:
		return _failure("dialogue_not_started")
	var selection_key: String = branch_id + ":" + choice_id
	# A repeated delivery of the same selected button is safe even when the first
	# delivery changes branch availability. The kernel owns the persisted ledger.
	if _submitted.has(selection_key):
		last_result = _world.dispatch_command(_submitted[selection_key].duplicate(true))
		return last_result.duplicate(true)
	var branch: Dictionary = selected_branch(dialogue_id)
	if str(branch.get("id", "")) != branch_id: return _failure("stale_branch")
	var command: String = ""
	for choice: Dictionary in branch.get("choices", []):
		if str(choice.id) == choice_id:
			command = str(choice.command)
			break
	if command.is_empty(): return _failure("unknown_choice")
	var action: Dictionary = {"id":_session_id + ":" + selection_key,"type":command}
	last_result = _world.dispatch_command(action)
	if last_result.ok: _submitted[selection_key] = action.duplicate(true)
	return last_result.duplicate(true)

func _failure(error: String) -> Dictionary:
	last_result = {"ok":false,"error":error}
	return last_result.duplicate(true)

static func release_dialogue_resource(resource: Resource) -> void:
	## DM 3.10.4 caches a back-reference in visited line dictionaries. Remove only
	## those transient references when the owner releases its dialogue resource.
	## Call after pending line requests finish, never while another view uses it.
	if resource == null: return
	var lines: Variant = resource.get("lines")
	if not lines is Dictionary: return
	for data: Variant in lines.values():
		if data is Dictionary and data.get("resource") == resource:
			data.erase("resource")
