extends SceneTree

const Navigation = preload("res://selected.gd")
var checks := 0
var failures: Array[String] = []

func check(condition: bool, label: String) -> void:
    checks += 1
    if not condition: failures.append(label)

func near(a: Vector2, b: Vector2, tolerance: float = 0.001) -> bool:
    return a.distance_to(b) <= tolerance

func _initialize() -> void:
    var nav = Navigation.new()
    check(not nav.is_configured(), "no implicit configuration")
    check(not nav.valid_ground(Vector2.ZERO), "unconfigured ground is invalid")
    check(nav.route(Vector2.ZERO, Vector2.ONE).is_empty(), "unconfigured route is empty")
    check(nav.move_ground(Vector2.ONE, Vector2.ONE) == Vector2.ONE, "unconfigured move stays put")
    check(nav.clamp_ground(Vector2.ONE) == Vector2.ONE, "unconfigured clamp stays put")
    check(nav.repair_ground(Vector2.ONE) == Vector2.ONE, "unconfigured repair stays put")
    check(not nav.configure(Rect2(), Vector2.ZERO, [], Vector2.ZERO).ok, "zero bounds rejected")
    check(not nav.is_configured(), "bad initial config leaves unconfigured")
    check(nav.configure(Rect2(0, 0, 120, 100), Vector2(2, 3), [], Vector2(10, 10)).ok, "empty geometry configured")
    check(nav.is_configured(), "configured query")
    check(nav.valid_ground(Vector2.ZERO), "bounds do not expand by half extents")
    check(nav.valid_ground(Vector2(120, 100)), "closed bounds allow exact contact")
    check(not nav.valid_ground(Vector2(-0.01, 0)), "outside bounds rejected")
    check(nav.route(Vector2(10, 10), Vector2(90, 80)) == [Vector2(90, 80)], "direct route")
    check(nav.route(Vector2(10, 10), Vector2(10, 10)).is_empty(), "same point route")
    check(nav.move_ground(Vector2(10, 10), Vector2(-100, 100)) == Vector2(0, 100), "bounds slide")
    check(nav.last_motion_segments.size() == 2, "bound contact and slide recorded")
    var obstacles: Array[Rect2] = [Rect2(40, 30, 20, 40)]
    check(nav.configure(Rect2(0, 0, 120, 100), Vector2(2, 3), obstacles, Vector2(10, 10)).ok, "obstacle configured")
    check(nav.last_motion_segments.is_empty(), "successful configuration resets motion")
    obstacles.clear()
    check(not nav.valid_ground(Vector2(40, 50)), "obstacle input not borrowed")
    check(not nav.valid_ground(Vector2(38, 50)), "half extent and skin inflation")
    check(nav.valid_ground(Vector2(37.98, 50)), "outside expanded obstacle valid")
    var moved: Vector2 = nav.move_ground(Vector2(10, 50), Vector2(1000, 0))
    check(near(moved, Vector2(37.98, 50)), "large sweep stops before solid; no tunneling")
    check(nav.last_motion_segments.size() == 1, "contact segment recorded")
    moved = nav.move_ground(Vector2(10, 10), Vector2(60, 60))
    check(moved.x > 37.97 and moved.x < 37.99 and moved.y > 69.98 and moved.y < 70.0, "diagonal solid slide")
    check(nav.last_motion_segments.size() == 2, "contact then slide")
    var sum := Vector2.ZERO
    for delta: Vector2 in nav.last_motion_segments: sum += delta
    check(near(Vector2(10, 10) + sum, moved), "motion segments sum to final position")
    check(not nav.segment_clear(Vector2(10, 50), Vector2(90, 50)), "crossing solid blocked")
    var route: Array[Vector2] = nav.route(Vector2(10, 50), Vector2(90, 50))
    check(route.size() >= 3 and route.back() == Vector2(90, 50), "route around obstacle")
    verify_route(nav, Vector2(10, 50), route)
    for iteration in 20:
        check(nav.route(Vector2(10, 50), Vector2(90, 50)) == route, "repeat route deterministic")
    var recorded: Array = nav.last_motion_segments.duplicate()
    var bad_configs: Array = [
        [Rect2(0, 0, -1, 1), Vector2.ZERO, [], Vector2.ZERO],
        [Rect2(Vector2(NAN, 0), Vector2.ONE), Vector2.ZERO, [], Vector2.ZERO],
        [Rect2(Vector2.ZERO, Vector2(INF, 1)), Vector2.ZERO, [], Vector2.ZERO],
        [Rect2(Vector2(3e38, 0), Vector2(3e38, 1)), Vector2.ZERO, [], Vector2.ZERO],
        [Rect2(0, 0, 120, 100), Vector2(-1, 0), [], Vector2(10, 10)],
        [Rect2(0, 0, 120, 100), Vector2(NAN, 0), [], Vector2(10, 10)],
        [Rect2(0, 0, 120, 100), Vector2(0, INF), [], Vector2(10, 10)],
        [Rect2(0, 0, 120, 100), Vector2.ZERO, [Rect2(30, 30, 0, 4)], Vector2(10, 10)],
        [Rect2(0, 0, 120, 100), Vector2.ZERO, [Rect2(30, 30, -1, 4)], Vector2(10, 10)],
        [Rect2(0, 0, 120, 100), Vector2.ZERO, [Rect2(Vector2(INF, 0), Vector2.ONE)], Vector2(10, 10)],
        [Rect2(0, 0, 120, 100), Vector2(3e38, 3e38), [Rect2(30, 30, 4, 4)], Vector2(10, 10)],
        [Rect2(0, 0, 120, 100), Vector2.ZERO, [], Vector2(121, 50)],
        [Rect2(0, 0, 120, 100), Vector2.ZERO, [], Vector2(NAN, 50)],
        [Rect2(0, 0, 120, 100), Vector2.ZERO, [Rect2(30, 30, 4, 4)], Vector2(32, 32)],
    ]
    for config: Array in bad_configs:
        var rects: Array[Rect2] = []
        rects.assign(config[2])
        var outcome: Dictionary = nav.configure(config[0], config[1], rects, config[3])
        check(not outcome.ok and not outcome.error.is_empty(), "bad config rejected with diagnostic")
        check(nav.route(Vector2(10, 50), Vector2(90, 50)) == route, "rejection preserves visibility graph")
        check(nav.last_motion_segments == recorded, "rejection preserves motion")
    check(nav.move_ground(Vector2(10, 10), Vector2(NAN, 0)) == Vector2(10, 10), "nonfinite motion rejected")
    check(nav.last_motion_segments.is_empty(), "rejected motion clears segments")
    check(nav.move_ground(Vector2(45, 45), Vector2.ONE) == Vector2(45, 45), "invalid start not teleported")
    check(nav.route(Vector2(45, 45), Vector2(10, 10)).is_empty(), "invalid route start not repaired implicitly")
    check(nav.route(Vector2(10, 10), Vector2(NAN, 0)).is_empty(), "nonfinite destination rejected")
    check(not nav.segment_clear(Vector2(10, 10), Vector2(INF, 0)), "nonfinite segment rejected")
    check(nav.clamp_ground(Vector2(INF, 0)) == Vector2(10, 10), "nonfinite clamp uses explicit spawn")
    check(nav.repair_ground(Vector2(NAN, 0)) == Vector2(10, 10), "nonfinite repair uses explicit spawn")
    check(nav.clamp_ground(Vector2(50, 50)) == Vector2(50, 50), "clamp does not repair solids")
    var repaired: Vector2 = nav.repair_ground(Vector2(50, 50))
    check(nav.valid_ground(repaired) and not nav.route(repaired, Vector2(10, 10)).is_empty(), "repair returns reachable ground")
    check(near(repaired, Vector2(37.98, 50)), "equidistant repair prefers lexicographic candidate")
    check(nav.repair_ground(Vector2(15, 15)) == Vector2(15, 15), "reachable valid point unchanged")
    check(nav.configure(Rect2(0, 0, 120, 100), Vector2(2, 1), [Rect2(50, -10, 10, 120)], Vector2(10, 50)).ok, "partition configured")
    check(nav.valid_ground(Vector2(90, 50)), "disconnected side is physically valid")
    check(nav.route(Vector2(10, 50), Vector2(90, 50)).is_empty(), "no route across partition")
    check(nav.route(Vector2(80, 50), Vector2(90, 50)) == [Vector2(90, 50)], "routing not limited to spawn component")
    repaired = nav.repair_ground(Vector2(90, 50))
    check(near(repaired, Vector2(47.98, 50)), "recovery selects nearest spawn-reachable component")
    check(nav.configure(Rect2(0, 0, 100, 100), Vector2.ZERO, [Rect2(40, 40, 20, 20)], Vector2(10, 10)).ok, "corner configured")
    moved = nav.move_ground(Vector2(10, 10), Vector2(100, 100))
    check(moved.x == moved.y and moved.x > 39.97 and moved.x < 39.99, "simultaneous corner hit stops both axes")
    check(nav.last_motion_segments.size() == 1, "corner produces one contact segment")
    check(nav.configure(Rect2(0, 0, 100, 100), Vector2.ZERO, [Rect2(40, 20, 20, 60)], Vector2(10, 50)).ok, "large delta layout configured")
    for magnitude: float in [1e20, 1e30, 3e38]:
        moved = nav.move_ground(Vector2(10, 50), Vector2(magnitude, 0))
        check(nav.valid_ground(moved) and near(moved, Vector2(39.98, 50)), "finite extreme delta preserves contact clearance")
    check(nav.configure(Rect2(1e6, 0, 120, 100), Vector2.ZERO, [Rect2(1e6 + 40, 30, 20, 40)], Vector2(1e6 + 10, 50)).ok, "large offset configured")
    moved = nav.move_ground(Vector2(1e6 + 10, 50), Vector2(100, 0))
    check(moved == Vector2(1e6 + 10, 50) and nav.last_motion_segments.is_empty(), "unrepresentable skin conservatively stops without teleport")
    exercise_narrow_gap(Vector2.ZERO, false)
    exercise_narrow_gap(Vector2(-60, 200), false)
    exercise_narrow_gap(Vector2(200, -60), true)
    check(nav.configure(Rect2(0, 0, 100, 100), Vector2.ZERO, [Rect2(40, -10, 20, 109.985)], Vector2(10, 10)).ok, "narrow boundary gap configured")
    var boundary_route: Array[Vector2] = nav.route(Vector2(10, 10), Vector2(90, 10))
    check(not boundary_route.is_empty(), "narrow obstacle-boundary passage routed")
    verify_route(nav, Vector2(10, 10), boundary_route)
    check(nav.repair_ground(Vector2(90, 10)) == Vector2(90, 10), "narrow boundary gap recovery preserves reachable point")
    exercise_layout(Rect2(-120, -90, 240, 180), Vector2(3, 5), [Rect2(-30, -35, 25, 75), Rect2(10, -10, 35, 25)], Vector2(-100, -70))
    exercise_layout(Rect2(250, -240, 90, 200), Vector2.ZERO, [Rect2(280, -200, 30, 30), Rect2(270, -150, 35, 20)], Vector2(255, -235))
    exercise_layout(Rect2(-30, 20, 180, 70), Vector2(1, 2), [Rect2(10, 35, 35, 20), Rect2(25, 30, 30, 30)], Vector2(-20, 25))
    if failures.is_empty():
        print("Scene navigation: %d checks passed" % checks)
        quit(0)
    else:
        for failure: String in failures: push_error(failure)
        print("Scene navigation: %d/%d checks failed" % [failures.size(), checks])
        quit(1)

func verify_route(nav: RefCounted, start: Vector2, route: Array[Vector2]) -> void:
    var point := start
    for next: Vector2 in route:
        check(nav.valid_ground(next) and nav.segment_clear(point, next), "route segment collision-free")
        point = next

func exercise_layout(bounds: Rect2, half: Vector2, obstacles: Array[Rect2], spawn: Vector2) -> void:
    var nav = Navigation.new()
    check(nav.configure(bounds, half, obstacles, spawn).ok, "alternate synthetic layout configured")
    var rng := RandomNumberGenerator.new()
    rng.seed = 314159
    for iteration in 160:
        var point := bounds.position + Vector2(rng.randf(), rng.randf()) * bounds.size
        var repaired: Vector2 = nav.repair_ground(point)
        check(nav.valid_ground(repaired), "sample repair valid")
        check(nav.repair_ground(repaired) == repaired, "sample repair idempotent")
        var travel: Array[Vector2] = nav.route(spawn, repaired)
        check(repaired == spawn or not travel.is_empty(), "sample repair reachable")
        verify_route(nav, spawn, travel)
        var displacement := Vector2(rng.randf_range(-500, 500), rng.randf_range(-500, 500))
        var moved: Vector2 = nav.move_ground(repaired, displacement)
        check(nav.valid_ground(moved), "sample swept motion valid")
        var origin := repaired
        for segment: Vector2 in nav.last_motion_segments:
            # Vector2 subtraction/addition can round a reconstructed bound contact
            # a few ulps outside; clamp only that reconstruction, not solid contact.
            check(nav.segment_clear(nav.clamp_ground(origin), nav.clamp_ground(origin + segment)), "sample motion segment clear")
            origin += segment
        check(near(origin, moved), "sample actual segments reconstruct motion")
        check(nav.move_ground(repaired, displacement) == moved, "sample motion repeat deterministic")

func exercise_narrow_gap(offset: Vector2, transpose: bool) -> void:
    var nav = Navigation.new()
    var start := Vector2(10, 10)
    var finish := Vector2(90, 10)
    var obstacles: Array[Rect2] = [Rect2(40, -10, 20, 60), Rect2(40, 50.025, 20, 60)]
    if transpose:
        start = Vector2(start.y, start.x)
        finish = Vector2(finish.y, finish.x)
        for index in obstacles.size():
            var rect := obstacles[index]
            obstacles[index] = Rect2(Vector2(rect.position.y, rect.position.x), Vector2(rect.size.y, rect.size.x))
    for index in obstacles.size(): obstacles[index].position += offset
    start += offset
    finish += offset
    check(nav.configure(Rect2(offset, Vector2(100, 100)), Vector2.ZERO, obstacles, start).ok, "sub-skin positive channel configured")
    var route: Array[Vector2] = nav.route(start, finish)
    check(not route.is_empty() and route.back() == finish, "sub-skin positive channel routed")
    verify_route(nav, start, route)
    check(nav.repair_ground(finish) == finish, "sub-skin channel preserves reachable endpoint")
    var repaired: Vector2 = nav.repair_ground(offset + Vector2(50, 50))
    check(nav.valid_ground(repaired) and not nav.route(start, repaired).is_empty(), "sub-skin repair remains reachable")
    for repeat in 10: check(nav.route(start, finish) == route, "sub-skin route deterministic")
