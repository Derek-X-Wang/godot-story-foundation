extends Node
## Optional presentation-only driver. Never advances dialogue, story time or saves.
## Host supplies flags; no assumptions about character IDs or narrative ownership.
var _portrait: Node2D
var _previous_process := false
var _enabled := false
const OWNER_KEY := &"_idle_host_adapter_owner"

func attach_portrait(value: Node2D) -> bool:
	if not is_inside_tree():
		return false
	if value == _portrait and is_instance_valid(value):
		return true
	if not is_instance_valid(value) or not value.is_node_ready() or not value.is_inside_tree():
		return false
	for method: StringName in [&"resume_motion", &"pause_motion", &"advance_motion"]:
		if not value.has_method(method):
			return false
	var previous_owner: Variant = value.get_meta(OWNER_KEY) if value.has_meta(OWNER_KEY) else null
	if previous_owner is WeakRef and is_instance_valid(previous_owner.get_ref()):
		return false
	if previous_owner != null and not previous_owner is WeakRef:
		return false
	detach_portrait()
	_portrait = value
	value.set_meta(OWNER_KEY, weakref(self))
	_previous_process = value.is_processing()
	value.set_process(false)
	_sync()
	return true

func detach_portrait() -> void:
	if is_instance_valid(_portrait):
		_portrait.pause_motion()
		_portrait.set_process(_previous_process)
		_portrait.remove_meta(OWNER_KEY)
	_portrait = null

func set_host_state(started: bool, paused: bool, backgrounded: bool,
		conversation_visible: bool, ending_visible: bool) -> void:
	_enabled = started and conversation_visible and not (paused or backgrounded or ending_visible)
	_sync()

func _sync() -> void:
	if not is_instance_valid(_portrait):
		return
	if _enabled and _portrait.is_inside_tree() and _portrait.is_visible_in_tree():
		_portrait.resume_motion()
	else:
		_portrait.pause_motion()

func tick(delta: float) -> void:
	if not is_finite(delta) or delta <= 0:
		return
	_sync()
	if is_instance_valid(_portrait):
		_portrait.advance_motion(delta)

func _process(delta: float) -> void:
	tick(delta)

func _exit_tree() -> void:
	detach_portrait()
