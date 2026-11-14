extends MeshInstance2D
## Optional grid assembler for prevalidated mesh_v1 manifests. No motion clock or art inference.
const MOTION_INCLUDE := preload("res://addons/story_foundation/presentation/portrait_idle_motion.gdshaderinc")
const SHADER_CODE := """
shader_type canvas_item;
#include "res://addons/story_foundation/presentation/portrait_idle_motion.gdshaderinc"
uniform float inhale = 0.0;
uniform vec4 breath_x;
uniform vec4 breath_y;
uniform vec2 breath_side;
uniform vec2 breath_displacement;
uniform bool has_elbow = false;
uniform vec2 elbow_pivot;
uniform float elbow_angle;
uniform vec4 elbow_x;
uniform vec4 elbow_y;
uniform vec2 pin_y;
float sf_band(float value, vec4 fade) {
    return smoothstep(fade.x, fade.y, value) * (1.0 - smoothstep(fade.z, fade.w, value));
}
void vertex() {
    vec2 p = VERTEX;
    float torso = sf_band(p.y, breath_y) * sf_band(p.x, breath_x);
    float side = clamp((p.x - breath_side.x) / breath_side.y, -1.0, 1.0);
    float arm = has_elbow ? sf_band(p.x, elbow_x) * sf_band(p.y, elbow_y) : 0.0;
    VERTEX = sf_idle_deform_point(p, inhale,
        vec2(side * breath_displacement.x, breath_displacement.y),
        elbow_pivot, elbow_angle, vec2(torso, arm), p.y <= pin_y.x || p.y >= pin_y.y);
}
"""
var idle_material: ShaderMaterial
var mat: ShaderMaterial ## Compatibility alias for existing consumer inspection.

func configure(record: Dictionary) -> void:
	assert(record.get("schema_version") == 1 and record.get("rig", {}).get("backend") == "mesh_v1")
	var dimensions: Array = record.canvas
	var width: int = dimensions[0]
	var height: int = dimensions[1]
	var step: int = record.rig.grid_px
	assert(width > 0 and height > 0 and step > 0 and width % step == 0 and height % step == 0)
	assert((width / step + 1) * (height / step + 1) <= 65536)
	texture = load("res://" + record.base)
	assert(texture is Texture2D and texture.get_width() == width and texture.get_height() == height)
	texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	var vertices := PackedVector2Array()
	var uvs := PackedVector2Array()
	var indices := PackedInt32Array()
	var cols := width / step + 1
	var rows := height / step + 1
	for j in range(rows):
		for i in range(cols):
			var p := Vector2(float(i * step), float(j * step))
			vertices.append(p)
			uvs.append(Vector2(p.x / width, p.y / height))
	for j in range(rows - 1):
		for i in range(cols - 1):
			var a := j * cols + i
			var b := a + 1
			var c := a + cols
			var d := c + 1
			indices.append_array(PackedInt32Array([a, b, d, a, d, c]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	var built := ArrayMesh.new()
	built.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh = built
	var shader := Shader.new()
	shader.code = SHADER_CODE
	idle_material = ShaderMaterial.new()
	mat = idle_material
	idle_material.shader = shader
	material = idle_material
	var breath: Dictionary = record.rig.breath
	var elbow_value: Variant = record.rig.get("elbow", null)
	var elbow: Dictionary = elbow_value if elbow_value is Dictionary else {}
	idle_material.set_shader_parameter("breath_x", _vec4(breath.x_fade))
	idle_material.set_shader_parameter("breath_y", _vec4(breath.y_fade))
	idle_material.set_shader_parameter("breath_side", Vector2(breath.side[0], breath.side[1]))
	idle_material.set_shader_parameter("breath_displacement", Vector2(breath.displacement[0], breath.displacement[1]))
	idle_material.set_shader_parameter("pin_y", Vector2(record.rig.pin_y[0], record.rig.pin_y[1]))
	idle_material.set_shader_parameter("has_elbow", not elbow.is_empty())
	if not elbow.is_empty():
		idle_material.set_shader_parameter("elbow_pivot", Vector2(elbow.pivot[0], elbow.pivot[1]))
		idle_material.set_shader_parameter("elbow_angle", elbow.angle_radians)
		idle_material.set_shader_parameter("elbow_x", _vec4(elbow.x_fade))
		idle_material.set_shader_parameter("elbow_y", _vec4(elbow.y_fade))
	set_inhale(0.0)

func set_inhale(value: float) -> void:
	if idle_material != null:
		idle_material.set_shader_parameter("inhale", clampf(value, 0.0, 1.0))

func _vec4(points: Array) -> Vector4:
	return Vector4(points[0], points[1], points[2], points[3])
