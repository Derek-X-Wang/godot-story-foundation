extends SceneTree
const Assembler = preload("res://addons/story_foundation/presentation/portrait_idle_mesh.gd")
var checks := 0
func check(value: bool, label: String) -> void:
	checks += 1
	assert(value, label)
func _initialize() -> void:
	call_deferred("run")
func run() -> void:
	var record := {
		"schema_version": 1, "base": "neutral.png", "canvas": [16, 16],
		"rig": {"backend": "mesh_v1", "grid_px": 4, "pin_y": [2, 12],
			"breath": {"x_fade": [1, 3, 13, 15], "y_fade": [2, 4, 10, 12],
				"side": [8, 4], "displacement": [0.2, -0.2]},
			"elbow": {"pivot": [11, 10], "angle_radians": -0.05,
				"x_fade": [9, 10, 13, 15], "y_fade": [4, 5, 11, 12]}}
	}
	var portrait = Assembler.new()
	root.add_child(portrait)
	portrait.configure(record)
	check(portrait.texture.get_size() == Vector2(16, 16), "texture loaded")
	check(portrait.mesh.get_surface_count() == 1, "one continuous grid")
	check(portrait.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX].size() == 25, "5 by 5 rest points")
	check(portrait.position == Vector2.ZERO and portrait.scale == Vector2.ONE, "root unmoved")
	check(portrait.mat == portrait.idle_material, "consumer material alias")
	portrait.set_inhale(1.0)
	check(portrait.mat.get_shader_parameter("inhale") == 1.0, "phase applied")
	portrait.set_inhale(0.0)
	check(portrait.mat.get_shader_parameter("inhale") == 0.0, "phase reset")
	var no_gesture_record: Dictionary = record.duplicate(true)
	no_gesture_record.rig.elbow = null
	var no_gesture = Assembler.new()
	root.add_child(no_gesture)
	no_gesture.configure(no_gesture_record)
	check(no_gesture.mesh.get_surface_count() == 1, "explicit null elbow still assembles")
	check(no_gesture.mat.get_shader_parameter("has_elbow") == false, "null elbow disables gesture")
	no_gesture_record.rig.erase("elbow")
	var absent_gesture = Assembler.new()
	root.add_child(absent_gesture)
	absent_gesture.configure(no_gesture_record)
	check(absent_gesture.mat.get_shader_parameter("has_elbow") == false, "absent elbow disables gesture")
	no_gesture.queue_free()
	absent_gesture.queue_free()
	portrait.queue_free()
	print("PASS: ", checks, " portrait-assembler assertions")
	quit()
