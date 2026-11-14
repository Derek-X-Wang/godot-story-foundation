# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
extends SceneTree
const Motion = preload("res://addons/story_foundation/presentation/portrait_idle_motion.gd")
var checks := 0

func _initialize() -> void:
    run.call_deferred()

func run() -> void:
    var viewport := SubViewport.new()
    viewport.size = Vector2i(8, 8)
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(viewport)
    var rect := ColorRect.new()
    rect.size = Vector2(8, 8)
    viewport.add_child(rect)
    var shader := Shader.new()
    shader.code = """shader_type canvas_item;
#include "res://addons/story_foundation/presentation/portrait_idle_motion.gdshaderinc"
#include "res://addons/story_foundation/presentation/portrait_idle_motion.gdshaderinc"
uniform vec2 rest_point;
uniform float inhale;
uniform vec2 displacement;
uniform vec2 pivot;
uniform float angle;
uniform vec2 weights;
uniform bool pinned;
uniform vec2 expected;
varying vec2 vertex_result;
void vertex() {
    vertex_result = sf_idle_deform_point(rest_point, inhale, displacement, pivot, angle, weights, pinned);
    // Support geometry stays put.
    VERTEX = sf_idle_deform_point(VERTEX, inhale, displacement, pivot, angle, weights, true);
}
bool match_point(vec2 result) {
    bvec2 nan_expected = isnan(expected);
    bvec2 inf_expected = isinf(expected);
    for (int i = 0; i < 2; i++) {
        if (nan_expected[i]) { if (!isnan(result[i])) return false; }
        else if (inf_expected[i]) { if (!isinf(result[i]) || sign(result[i]) != sign(expected[i])) return false; }
        else if (isnan(result[i]) || isinf(result[i]) || abs(result[i] - expected[i]) > 0.0002) return false;
    }
    return true;
}
void fragment() {
    vec2 result = sf_idle_deform_point(rest_point, inhale, displacement, pivot, angle, weights, pinned);
    bool ok = match_point(result) && (sf_idle_invalid(rest_point) || match_point(vertex_result));
    COLOR = ok ? vec4(0.0, 1.0, 0.0, 1.0) : vec4(1.0, 0.0, 0.0, 1.0);
}
"""
    var material := ShaderMaterial.new()
    material.shader = shader
    rect.material = material
    for i in range(49):
        for weights in [Vector2.ONE, Vector2(-1, 2), Vector2.ZERO, Vector2(0.3, 0.7)]:
            await check(material, viewport, [Vector2(42, 57), Motion.breath(i / 48.0), Vector2(2, -3), Vector2(30, 40), -0.12, weights, false])
    for phase in [-1.0, 2.0]:
        await check(material, viewport, [Vector2(42, 57), phase, Vector2(2, -3), Vector2(30, 40), -0.12, Vector2.ONE, false])
    await check(material, viewport, [Vector2(42, 57), 1.0, Vector2(2, -3), Vector2(30, 40), -0.12, Vector2.ONE, true])
    for invalid in [NAN, INF, -INF]:
        for field in [1, 2, 3, 4, 5]:
            var args := [Vector2(42, 57), 1.0, Vector2(2, -3), Vector2(30, 40), -0.12, Vector2.ONE, false]
            args[field] = invalid if field in [1, 4] else Vector2(invalid, 0)
            await check(material, viewport, args)
        for field in [0, 2, 3, 5]:
            var args := [Vector2(42, 57), 1.0, Vector2(2, -3), Vector2(30, 40), -0.12, Vector2.ONE, false]
            args[field] = Vector2(0, invalid)
            await check(material, viewport, args)
        await check(material, viewport, [Vector2(invalid, 0), 1.0, Vector2(2, -3), Vector2(30, 40), -0.12, Vector2.ONE, false])
    print("PASS: %d GPU portrait-motion assertions" % checks)
    quit(0)

func check(material: ShaderMaterial, viewport: SubViewport, args: Array) -> void:
    var names := ["rest_point", "inhale", "displacement", "pivot", "angle", "weights", "pinned"]
    for i in names.size():
        material.set_shader_parameter(names[i], args[i])
    var expected: Vector2 = Motion.deform_point.callv(args)
    material.set_shader_parameter("expected", expected)
    await process_frame
    await RenderingServer.frame_post_draw
    var image := viewport.get_texture().get_image()
    if image == null or image.is_empty():
        push_error("GPU test requires actual rendering, not the headless dummy renderer")
        quit(1)
        return
    for y in image.get_height():
        for x in image.get_width():
            var color := image.get_pixel(x, y)
            if color.g < 0.99 or color.r > 0.01 or color.a < 0.99:
                push_error("GPU mismatch in case %d: %s, pixel %s" % [checks, args, color])
                quit(1)
                return
    checks += 1
