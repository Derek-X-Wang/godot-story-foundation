# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang

## Preserved presentation fixture for the original authority/lifetime regression tests.
extends Control
signal landmark_clicked(label: String)
var scene_id: String = "village"
var player := Vector2(340,270)
var time: float = 0.0
var locations: Array = []
var world: Dictionary = {}
var palette := {"village":Color("263d38"),"forest":Color("203b36"),"clinic":Color("3c3942"),"storehouse":Color("3f3a30")}

func _ready() -> void:
	custom_minimum_size = Vector2(640,350)
	mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	mouse_filter = Control.MOUSE_FILTER_STOP
	gui_input.connect(_on_input)

func set_world(data: Dictionary) -> void:
	world = data
	scene_id = data.scene
	locations.clear()
	match scene_id:
		"village": locations = [{"pos":Vector2(140,115),"name":"HEALER","color":Color("e7c081")},{"pos":Vector2(480,130),"name":"GUARD","color":Color("8eb8d0")},{"pos":Vector2(430,270),"name":"WITNESS","color":Color("b6a3d4")}]
		"forest": locations = [{"pos":Vector2(420,160),"name":"MEDICINAL HERBS","color":Color("a3d990")}]
		"clinic": locations = [{"pos":Vector2(360,140),"name":"PATIENT","color":Color("d99586")}]
		"storehouse": locations = [{"pos":Vector2(380,170),"name":"VILLAGE STORES","color":Color("e7c081")}]
	queue_redraw()

func _process(delta: float) -> void:
	time += delta
	var direction := Vector2(float(Input.is_physical_key_pressed(KEY_D) or Input.is_key_pressed(KEY_RIGHT))-float(Input.is_physical_key_pressed(KEY_A) or Input.is_key_pressed(KEY_LEFT)),float(Input.is_physical_key_pressed(KEY_S) or Input.is_key_pressed(KEY_DOWN))-float(Input.is_physical_key_pressed(KEY_W) or Input.is_key_pressed(KEY_UP)))
	if direction != Vector2.ZERO:
		player += direction.normalized()*delta*145
		player.x = clampf(player.x,35,605)
		player.y = clampf(player.y,50,315)
	queue_redraw()

func _on_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed and event.button_index==MOUSE_BUTTON_LEFT:
		var point: Vector2 = event.position / (size/Vector2(640,350))
		for item: Dictionary in locations:
			if point.distance_to(item.pos)<55:
				landmark_clicked.emit(item.name)
				return
		player = Vector2(clampf(point.x,35,605),clampf(point.y,50,315))

func _draw() -> void:
	var scale_2d := size/Vector2(640,350)
	draw_set_transform(Vector2.ZERO,0,scale_2d)
	draw_rect(Rect2(0,0,640,350),palette.get(scene_id,Color("263d38")))
	# Readable placeholder scenery built from primitive geometry; no imported artwork.
	for x: int in range(20,640,40):
		for y: int in range(20,350,40):
			draw_circle(Vector2(x,y),1,Color(0.65,0.8,0.65,0.10))
	if scene_id in ["village","forest"]:
		draw_colored_polygon(PackedVector2Array([Vector2(265,350),Vector2(365,350),Vector2(365,210),Vector2(640,230),Vector2(640,185),Vector2(355,165),Vector2(320,0),Vector2(275,0)]),Color("53604b"))
		for i: int in range(11):
			var p := Vector2(35+(i*113)%580,30+(i*71)%280)
			if absf(p.x-320)>100:
				draw_circle(p+Vector2(3,6),22,Color(0,0,0,0.18))
				draw_circle(p,21,Color("315745"))
				draw_circle(p+Vector2(-5,-5),12,Color("416b50"))
	if scene_id=="village":
		_building(Vector2(65,65),Vector2(160,95),Color("a68262"))
		_building(Vector2(420,65),Vector2(160,95),Color("76857f"))
	if scene_id=="clinic":
		draw_rect(Rect2(80,55,480,235),Color("575058"))
		draw_rect(Rect2(308,90,105,105),Color("bba89a"))
		draw_rect(Rect2(316,116,89,65),Color("d1bba4"))
	if scene_id=="storehouse":
		for p: Vector2 in [Vector2(120,110),Vector2(460,110),Vector2(470,240)]:
			draw_rect(Rect2(p,Vector2(65,55)),Color("8f704b"))
			draw_rect(Rect2(p+Vector2(5,5),Vector2(55,45)),Color("b49563"),false,2)
	var font: Font = ThemeDB.fallback_font
	for item: Dictionary in locations:
		draw_circle(item.pos+Vector2(0,9),15,Color(0,0,0,0.25))
		draw_circle(item.pos,10,item.color)
		draw_arc(item.pos,19+sin(time*2)*2,0,TAU,32,Color(item.color,0.35),1.5)
		var label_width: float = font.get_string_size(item.name,HORIZONTAL_ALIGNMENT_LEFT,-1,11).x
		draw_string(font,item.pos+Vector2(-label_width/2,-28),item.name,HORIZONTAL_ALIGNMENT_LEFT,-1,11,Color("e7e8dd"))
	draw_circle(player+Vector2(0,9),12,Color(0,0,0,0.3))
	draw_circle(player,9,Color("efe8c8"))
	draw_circle(player+Vector2(-2,-2),3,Color("ffffff"))
	draw_string(font,player+Vector2(-13,27),"YOU",HORIZONTAL_ALIGNMENT_LEFT,-1,10,Color("e7e8dd"))
	draw_set_transform(Vector2.ZERO,0,Vector2.ONE)

func _building(at: Vector2,extent: Vector2,color: Color) -> void:
	draw_rect(Rect2(at+Vector2(7,10),extent),Color(0,0,0,0.25))
	draw_rect(Rect2(at,extent),color)
	draw_colored_polygon(PackedVector2Array([at+Vector2(-10,0),at+Vector2(extent.x/2,-35),at+Vector2(extent.x+10,0)]),color.darkened(0.24))
	draw_rect(Rect2(at+Vector2(extent.x/2-13,extent.y-38),Vector2(26,38)),Color("29372f"))
