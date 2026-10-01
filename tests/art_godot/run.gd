# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
# A bare-project consumer: deliberately no Foundation or dialogue dependencies.
extends SceneTree

var failures: int = 0
var checks: int = 0

func _initialize() -> void:
	call_deferred("run")

func check(label: String, condition: bool) -> void:
	checks += 1
	if not condition:
		failures += 1
		printerr("FAIL: ", label)

func run() -> void:
	var fixture_paths: Array = JSON.parse_string(FileAccess.get_file_as_string("res://fixture_paths.json"))
	for directory: String in fixture_paths:
		await inspect_fixture(directory)
	print("Art Godot consumer: %d checks, %d failures" % [checks, failures])
	quit(1 if failures else 0)

func inspect_fixture(directory: String) -> void:
	var prefix: String = directory + "/"
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(prefix + "atlas.json"))
	var expected: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(prefix + "expected.json"))
	var frames: SpriteFrames = load(prefix + "sprite_frames.tres")
	check(directory + " loads SpriteFrames", frames != null)
	if frames == null:
		return
	check(directory + " escaped resource name", frames.resource_name == expected.asset_id)
	check(directory + " animation count", frames.get_animation_names().size() == data.tags.size())
	var original: Image = Image.load_from_file(prefix + "atlas.png")
	check(directory + " raw PNG size", original.get_size() == Vector2i(expected.width, expected.height))
	var raw_pixels_match: bool = true
	for y in expected.height:
		for x in expected.width:
			var rgba: Array = expected.pixels[y * int(expected.width) + x]
			var color: Color = Color8(rgba[0], rgba[1], rgba[2], rgba[3])
			raw_pixels_match = raw_pixels_match and original.get_pixel(x, y).is_equal_approx(color)
	check(directory + " exact original source pixels", raw_pixels_match)

	for tag: Dictionary in data.tags:
		var animation: StringName = StringName(tag.name)
		check(directory + " tag exists " + tag.name, frames.has_animation(animation))
		if not frames.has_animation(animation):
			continue
		check(tag.name + " frame count", frames.get_frame_count(animation) == int(tag.count))
		check(tag.name + " loop", frames.get_animation_loop(animation) == tag.loop)
		check(tag.name + " FPS", is_equal_approx(frames.get_animation_speed(animation), 1000.0))
		for local_index in tag.count:
			var frame: Dictionary = data.frames[int(tag.start) + local_index]
			var texture: AtlasTexture = frames.get_frame_texture(animation, local_index) as AtlasTexture
			check(tag.name + " AtlasTexture", texture != null)
			if texture == null:
				continue
			var rect: Array = frame.rect
			check(tag.name + " region", texture.region == Rect2(rect[0], rect[1], rect[2], rect[3]))
			check(tag.name + " unscaled frame size", texture.get_size() == Vector2(data.cell[0], data.cell[1]))
			check(tag.name + " clipping", texture.filter_clip)
			check(tag.name + " relative texture path", texture.atlas.resource_path == prefix + "atlas.png")
			var relative_duration: float = frames.get_frame_duration(animation, local_index)
			check(tag.name + " millisecond duration", is_equal_approx(relative_duration, tag.durations_ms[local_index]))
			check(tag.name + " exact timing", is_equal_approx(relative_duration / frames.get_animation_speed(animation), float(tag.durations_ms[local_index]) / 1000.0))
			var imported: Image = texture.atlas.get_image()
			var pixels_match: bool = true
			for y in int(rect[3]):
				for x in int(rect[2]):
					var source: Color = original.get_pixel(int(rect[0]) + x, int(rect[1]) + y)
					var pixel: Color = imported.get_pixel(int(rect[0]) + x, int(rect[1]) + y)
					# Godot's default alpha-border fix may fill RGB under zero alpha.
					# Compare visible RGBA and all alpha; the source check above is exact.
					pixels_match = pixels_match and is_equal_approx(pixel.a, source.a)
					if source.a > 0.0:
						pixels_match = pixels_match and pixel.is_equal_approx(source)
			check(tag.name + " imported visible source pixels", pixels_match)

	var scene: PackedScene = load(prefix + "preview.tscn")
	check(directory + " loads preview", scene != null)
	if scene == null:
		return
	var sprite: AnimatedSprite2D = scene.instantiate() as AnimatedSprite2D
	check(directory + " native AnimatedSprite2D", sprite != null)
	if sprite == null:
		return
	root.add_child(sprite)
	sprite.position = Vector2(64, 64)
	check(directory + " nearest filtering", sprite.texture_filter == CanvasItem.TEXTURE_FILTER_NEAREST)
	check(directory + " default scale", sprite.scale == Vector2.ONE)
	check(directory + " centered", sprite.centered)
	var cell: Vector2 = Vector2(data.cell[0], data.cell[1])
	var pivot: Vector2 = Vector2(data.pivot[0], data.pivot[1])
	check(directory + " pixel pivot offset", sprite.offset == cell / 2.0 - pivot)
	check(directory + " pivot is node origin", -cell / 2.0 + sprite.offset + pivot == Vector2.ZERO)
	check(directory + " no runtime script", sprite.get_script() == null)
	check(directory + " initial tag", sprite.animation == StringName(data.tags[0].name))
	check(directory + " autoplay", sprite.autoplay == data.tags[0].name and sprite.is_playing())
	for tag: Dictionary in data.tags:
		await inspect_playback(sprite, tag, directory)
	sprite.queue_free()
	await process_frame

func inspect_playback(sprite: AnimatedSprite2D, tag: Dictionary, directory: String) -> void:
	# The runner uses --fixed-fps 1000: one process tick is exactly one millisecond.
	# Observe real AnimatedSprite2D playback rather than only inspecting metadata.
	sprite.stop()
	var changes: Array = []
	var events: Dictionary = {"loops": 0, "finishes": 0}
	var changed: Callable = func() -> void:
		changes.append({"frame": sprite.frame, "tick": Engine.get_process_frames()})
	var looped: Callable = func() -> void: events.loops += 1
	var finished: Callable = func() -> void: events.finishes += 1
	sprite.frame_changed.connect(changed)
	sprite.animation_looped.connect(looped)
	sprite.animation_finished.connect(finished)
	sprite.play(StringName(tag.name))
	sprite.set_frame_and_progress(0, 0.0)
	changes.clear()
	changes.append({"frame": 0, "tick": Engine.get_process_frames()})
	var total_ms: int = 0
	for duration: float in tag.durations_ms:
		total_ms += int(duration)
	var budget: int = total_ms * (2 if tag.loop else 1) + 5
	for tick in budget:
		await process_frame
	check(directory + " " + tag.name + " advances", changes.size() >= int(tag.count))
	var first_cycle: bool = changes.size() >= int(tag.count)
	for index in mini(changes.size(), int(tag.count)):
		first_cycle = first_cycle and changes[index].frame == index
	check(tag.name + " forward frame order", first_cycle)
	var timing: bool = true
	for index in range(1, mini(changes.size(), int(tag.count) + 1)):
		var elapsed: int = int(changes[index].tick) - int(changes[index - 1].tick)
		timing = timing and absi(elapsed - int(tag.durations_ms[index - 1])) <= 2
	check(tag.name + " playback uses nonuniform millisecond durations", timing)
	if tag.loop:
		check(tag.name + " looped during playback", events.loops >= 1 and events.finishes == 0 and sprite.is_playing())
	else:
		check(tag.name + " finishes exactly once", events.finishes == 1 and events.loops == 0)
		check(tag.name + " stops at last frame", not sprite.is_playing() and sprite.frame == int(tag.count) - 1)
	sprite.frame_changed.disconnect(changed)
	sprite.animation_looped.disconnect(looped)
	sprite.animation_finished.disconnect(finished)
