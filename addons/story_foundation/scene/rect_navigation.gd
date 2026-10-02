# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
extends RefCounted
## Optional axis-aligned foot-anchor navigation. No scene, assets or runtime required.
## API version 1. Configure explicitly before querying; bounds already describe
## allowed anchors. Obstacles alone expand by half-extents plus the contact skin.

const API_VERSION := 1
const EPS := 0.01
const TIME_EPS := 0.0000001
## Actual swept displacements, including a contact segment followed by a slide.
## Cleared by every move attempt and every successful configure.
var last_motion_segments: Array[Vector2] = []
var _configured := false
var _bounds := Rect2()
var _safe_spawn := Vector2.ZERO
var _solids: Array[Rect2] = []
var _nodes: Array[Vector2] = []
var _links: Array[Array] = []
var _spawn_component: Array[bool] = []

## Invalid configuration leaves all previous geometry and motion data unchanged.
func configure(bounds: Rect2, half_extents: Vector2, obstacles: Array[Rect2], safe_spawn: Vector2) -> Dictionary:
    if not _finite_positive_rect(bounds):
        return {"ok": false, "error": "bounds must have finite coordinates/end and positive size"}
    if not half_extents.is_finite() or half_extents.x < 0.0 or half_extents.y < 0.0:
        return {"ok": false, "error": "half_extents must be finite and nonnegative"}
    if not safe_spawn.is_finite():
        return {"ok": false, "error": "safe_spawn must be finite"}
    var solids: Array[Rect2] = []
    for index in obstacles.size():
        var footprint := obstacles[index]
        if not _finite_positive_rect(footprint):
            return {"ok": false, "error": "obstacle %d must have finite coordinates/end and positive size" % index}
        var solid := footprint.grow_individual(half_extents.x + EPS, half_extents.y + EPS, half_extents.x + EPS, half_extents.y + EPS)
        if not _finite_positive_rect(solid):
            return {"ok": false, "error": "expanded obstacle %d must remain finite" % index}
        solids.append(solid)
    if safe_spawn.x < bounds.position.x or safe_spawn.x > bounds.end.x or safe_spawn.y < bounds.position.y or safe_spawn.y > bounds.end.y:
        return {"ok": false, "error": "safe_spawn must lie within bounds"}
    for solid: Rect2 in solids:
        if _inside_closed(safe_spawn, solid):
            return {"ok": false, "error": "safe_spawn must be outside expanded obstacles"}
    _bounds = bounds
    _safe_spawn = safe_spawn
    _solids = solids
    _configured = true
    last_motion_segments.clear()
    _build_visibility_graph()
    return {"ok": true, "error": ""}

func is_configured() -> bool:
    return _configured

func _finite_positive_rect(rect: Rect2) -> bool:
    return rect.position.is_finite() and rect.size.is_finite() and rect.end.is_finite() and rect.size.x > 0.0 and rect.size.y > 0.0

func valid_ground(point: Vector2) -> bool:
    if not _configured or not point.is_finite(): return false
    if point.x < _bounds.position.x or point.x > _bounds.end.x or point.y < _bounds.position.y or point.y > _bounds.end.y:
        return false
    for solid: Rect2 in _solids:
        if _inside_closed(point, solid): return false
    return true

func clamp_ground(point: Vector2) -> Vector2:
    if not _configured: return point
    if not point.is_finite(): return _safe_spawn
    return Vector2(clampf(point.x, _bounds.position.x, _bounds.end.x), clampf(point.y, _bounds.position.y, _bounds.end.y))

func repair_ground(point: Vector2) -> Vector2:
    if not _configured: return point
    # Explicit recovery only: route() and move_ground() never teleport endpoints.
    if not point.is_finite(): return _safe_spawn
    if valid_ground(point) and _connected_to_spawn(point): return point
    var candidates := _repair_candidates(point)
    var best := _safe_spawn
    var best_distance := point.distance_squared_to(best)
    for candidate: Vector2 in candidates:
        if not valid_ground(candidate) or not _connected_to_spawn(candidate): continue
        var distance := point.distance_squared_to(candidate)
        if distance < best_distance - TIME_EPS or (absf(distance - best_distance) <= TIME_EPS and _lex_less(candidate, best)):
            best = candidate
            best_distance = distance
    return best

func segment_clear(a: Vector2, b: Vector2) -> bool:
    if not valid_ground(a) or not valid_ground(b): return false
    # A rectangle is convex: valid endpoints guarantee the segment stays in _bounds.
    var delta := b - a
    for solid: Rect2 in _solids:
        if not _sweep_rect(a, delta, solid).is_empty(): return false
    return true

func move_ground(start: Vector2, displacement: Vector2) -> Vector2:
    last_motion_segments.clear()
    if not valid_ground(start) or not displacement.is_finite(): return start
    var point := start
    var remaining := displacement
    # Each hit removes at least one velocity axis, so two collisions suffice.
    for unused in range(3):
        if remaining.length_squared() < TIME_EPS * TIME_EPS: break
        var hit := _first_hit(point, remaining)
        if hit.is_empty():
            var proposed := point + remaining
            if not proposed.is_finite(): return point
            var finish := clamp_ground(proposed)
            if not valid_ground(finish): return point
            last_motion_segments.append(finish - point)
            point = finish
            break
        var fraction: float = hit.t
        # Stay a tiny distance before a closed solid. Bounds permit exact contact.
        var advance_fraction := fraction
        if hit.solid:
            var length := remaining.length()
            # Vector2 length uses float32 and may overflow for a finite delta.
            # Preserve the original arithmetic for ordinary scene displacements.
            if not is_finite(length):
                length = sqrt(float(remaining.x) * float(remaining.x) + float(remaining.y) * float(remaining.y))
            advance_fraction = maxf(0.0, fraction - EPS / maxf(length, EPS))
        var proposed := point + remaining * advance_fraction
        if not proposed.is_finite(): return point
        var next_point := clamp_ground(proposed)
        # At enormous coordinates the contact skin can round away in Vector2.
        # Conservatively stop at the last valid point rather than enter a solid.
        if not valid_ground(next_point): return point
        var step := next_point - point
        if not step.is_zero_approx():
            last_motion_segments.append(step)
            point = next_point
        remaining *= 1.0 - fraction
        if hit.x: remaining.x = 0.0
        if hit.y: remaining.y = 0.0
    point = clamp_ground(point)
    assert(valid_ground(point), "Swept scene movement must finish on valid ground")
    return point

func route(start: Vector2, end: Vector2) -> Array[Vector2]:
    # Waypoints exclude start and include end. Empty means no travel or no route.
    var result: Array[Vector2] = []
    if not valid_ground(start) or not valid_ground(end): return result
    if start == end: return result
    if segment_clear(start, end):
        result.append(end)
        return result
    var points: Array[Vector2] = [start, end]
    points.append_array(_nodes)
    var adjacency: Array[Array] = [[], []]
    for i in _nodes.size():
        var edges: Array = []
        for edge: Dictionary in _links[i]:
            edges.append({"to": int(edge.to) + 2, "cost": edge.cost})
        adjacency.append(edges)
    for endpoint in range(2):
        for i in _nodes.size():
            if segment_clear(points[endpoint], _nodes[i]):
                var cost := points[endpoint].distance_to(_nodes[i])
                adjacency[endpoint].append({"to": i + 2, "cost": cost})
                adjacency[i + 2].append({"to": endpoint, "cost": cost})
    var distances := PackedFloat64Array()
    var previous := PackedInt32Array()
    var visited := PackedByteArray()
    distances.resize(points.size()); distances.fill(INF); distances[0] = 0.0
    previous.resize(points.size()); previous.fill(-1)
    visited.resize(points.size()); visited.fill(0)
    for unused in points.size():
        var selected := -1
        var minimum := INF
        for i in points.size():
            if visited[i] == 0 and distances[i] < minimum:
                selected = i
                minimum = distances[i]
        if selected == -1: return result
        if selected == 1: break
        visited[selected] = 1
        for edge: Dictionary in adjacency[selected]:
            var next: int = edge.to
            var distance: float = distances[selected] + edge.cost
            if distance < distances[next] - TIME_EPS:
                distances[next] = distance
                previous[next] = selected
    if previous[1] == -1: return result
    var cursor := 1
    while cursor != 0:
        result.append(points[cursor])
        cursor = previous[cursor]
    result.reverse()
    return result

func _build_visibility_graph() -> void:
    _nodes.clear()
    _links.clear()
    _add_node(_safe_spawn)
    for x: float in [_bounds.position.x, _bounds.end.x]:
        for y: float in [_bounds.position.y, _bounds.end.y]: _add_node(Vector2(x, y))
    for solid: Rect2 in _solids:
        for x: float in [solid.position.x - EPS, solid.end.x + EPS]:
            for y: float in [solid.position.y - EPS, solid.end.y + EPS]:
                _add_node(clamp_ground(Vector2(x, y)))
    # Fixed corner offsets can miss a positive channel narrower than 2 * EPS.
    # Extra midpoint nodes only affect those channels, preserving normal layouts.
    for point: Vector2 in _narrow_gap_candidates(): _add_node(point)
    for unused in _nodes.size(): _links.append([])
    for i in _nodes.size():
        for j in range(i + 1, _nodes.size()):
            if segment_clear(_nodes[i], _nodes[j]):
                var distance := _nodes[i].distance_to(_nodes[j])
                _links[i].append({"to": j, "cost": distance})
                _links[j].append({"to": i, "cost": distance})
    _spawn_component.clear()
    _spawn_component.resize(_nodes.size())
    _spawn_component.fill(false)
    if _nodes.is_empty(): return
    var pending: Array[int] = [0]
    _spawn_component[0] = true
    while not pending.is_empty():
        var index: int = pending.pop_back()
        for edge: Dictionary in _links[index]:
            var next: int = edge.to
            if not _spawn_component[next]:
                _spawn_component[next] = true
                pending.append(next)

func _add_node(point: Vector2) -> void:
    if not valid_ground(point): return
    for existing: Vector2 in _nodes:
        if point.distance_squared_to(existing) < TIME_EPS: return
    _nodes.append(point)

func _connected_to_spawn(point: Vector2) -> bool:
    if not valid_ground(point): return false
    for i in _nodes.size():
        if _spawn_component[i] and segment_clear(point, _nodes[i]): return true
    return false

func _repair_candidates(point: Vector2) -> Array[Vector2]:
    # Orthogonal projections plus all boundary intersections cover the nearest
    # point of axis-aligned free space, including overlapping rectangle unions.
    var candidates: Array[Vector2] = [clamp_ground(point), _safe_spawn]
    var xs: Array[float] = [_bounds.position.x, _bounds.end.x]
    var ys: Array[float] = [_bounds.position.y, _bounds.end.y]
    for solid: Rect2 in _solids:
        xs.append(solid.position.x - EPS); xs.append(solid.end.x + EPS)
        ys.append(solid.position.y - EPS); ys.append(solid.end.y + EPS)
    for x: float in xs:
        candidates.append(clamp_ground(Vector2(x, point.y)))
        for y: float in ys: candidates.append(clamp_ground(Vector2(x, y)))
    for y: float in ys: candidates.append(clamp_ground(Vector2(point.x, y)))
    candidates.append_array(_narrow_gap_candidates(point, true))
    return candidates

func _narrow_gap_candidates(point: Vector2 = Vector2.ZERO, project_point: bool = false) -> Array[Vector2]:
    var xs: Array[float] = [_bounds.position.x, _bounds.end.x]
    var ys: Array[float] = [_bounds.position.y, _bounds.end.y]
    var x_edges := xs.duplicate()
    var y_edges := ys.duplicate()
    for solid: Rect2 in _solids:
        xs.append(solid.position.x - EPS); xs.append(solid.end.x + EPS)
        ys.append(solid.position.y - EPS); ys.append(solid.end.y + EPS)
        x_edges.append(solid.position.x); x_edges.append(solid.end.x)
        y_edges.append(solid.position.y); y_edges.append(solid.end.y)
    var narrow_x := _narrow_midpoints(x_edges)
    var narrow_y := _narrow_midpoints(y_edges)
    ys.append_array(narrow_y)
    if project_point:
        xs.append(point.x)
        ys.append(point.y)
    var result: Array[Vector2] = []
    for x: float in narrow_x:
        for y: float in ys: result.append(clamp_ground(Vector2(x, y)))
    for y: float in narrow_y:
        for x: float in xs: result.append(clamp_ground(Vector2(x, y)))
    return result

func _narrow_midpoints(edges: Array[float]) -> Array[float]:
    edges.sort()
    var result: Array[float] = []
    for index in range(1, edges.size()):
        var low := edges[index - 1]
        var high := edges[index]
        if high > low and high - low < 2.0 * EPS:
            var middle := low + (high - low) * 0.5
            if middle > low and middle < high: result.append(middle)
    return result

func _inside_closed(point: Vector2, rect: Rect2) -> bool:
    return point.x >= rect.position.x and point.x <= rect.end.x and point.y >= rect.position.y and point.y <= rect.end.y

func _lex_less(a: Vector2, b: Vector2) -> bool:
    return a.x < b.x or (a.x == b.x and a.y < b.y)

func _sweep_rect(start: Vector2, delta: Vector2, rect: Rect2) -> Dictionary:
    var entry := -INF
    var leave := INF
    var x_entry := -INF
    var y_entry := -INF
    for axis in range(2):
        if absf(delta[axis]) < TIME_EPS:
            if start[axis] < rect.position[axis] or start[axis] > rect.end[axis]: return {}
            continue
        var near_time := (rect.position[axis] - start[axis]) / delta[axis]
        var far_time := (rect.end[axis] - start[axis]) / delta[axis]
        if near_time > far_time:
            var swap := near_time
            near_time = far_time
            far_time = swap
        if axis == 0: x_entry = near_time
        else: y_entry = near_time
        entry = maxf(entry, near_time)
        leave = minf(leave, far_time)
        if entry > leave: return {}
    if leave < 0.0 or entry > 1.0: return {}
    return {"t": maxf(0.0, entry), "x": absf(x_entry - entry) <= TIME_EPS, "y": absf(y_entry - entry) <= TIME_EPS, "solid": true}

func _first_hit(start: Vector2, delta: Vector2) -> Dictionary:
    var best: Dictionary = {}
    for axis in range(2):
        var finish: float = start[axis] + delta[axis]
        var limit: float = _bounds.position[axis] if delta[axis] < 0 else _bounds.end[axis]
        if (delta[axis] < 0 and finish < limit) or (delta[axis] > 0 and finish > limit):
            best = _earlier_hit(best, {"t": (limit - start[axis]) / delta[axis], "x": axis == 0, "y": axis == 1, "solid": false})
    for solid: Rect2 in _solids:
        best = _earlier_hit(best, _sweep_rect(start, delta, solid))
    return best

func _earlier_hit(a: Dictionary, b: Dictionary) -> Dictionary:
    if b.is_empty(): return a
    if a.is_empty() or float(b.t) < float(a.t) - TIME_EPS: return b
    if absf(float(a.t) - float(b.t)) <= TIME_EPS:
        return {"t": minf(a.t, b.t), "x": a.x or b.x, "y": a.y or b.y, "solid": a.solid or b.solid}
    return a
