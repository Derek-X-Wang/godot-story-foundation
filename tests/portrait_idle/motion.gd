extends SceneTree
const Motion = preload("res://addons/story_foundation/presentation/portrait_idle_motion.gd")
var checks := 0
func check(value: bool, reason: String) -> void:
	checks += 1
	if not value:
		push_error(reason)
		quit(1)
		assert(value, reason)
func _initialize() -> void:
	check(Motion.breath(0) == 0 and Motion.breath(1) == 0, "loop endpoints")
	check(is_equal_approx(Motion.breath(0.5), 1), "inhale peak")
	check(is_equal_approx(Motion.breath(-0.25), Motion.breath(0.75)), "wrapped phase")
	check(Motion.breath(NAN) == 0 and Motion.breath(INF) == 0, "invalid phase")
	check(Motion.blink(0.1, 0.2, false) == 0, "no invented eyelid")
	check(Motion.blink(0.1, 0.2, true) > 0.99, "authored eyelid pulse")
	for t in [-1.0, 0.0, 0.2, INF, NAN]:
		check(Motion.blink(t, 0.2, true) == 0, "blink outside active interval")
	check(Motion.blink(0.1, 0, true) == 0, "invalid duration")
	check(Motion.gaze(Vector2.ONE, Vector2(2, 3), false) == Vector2.ZERO, "no invented iris")
	check(Motion.gaze(Vector2(5, -4), Vector2(2, 3), true) == Vector2(2, -3), "bounded authored iris")
	check(Motion.gaze(Vector2(NAN, 0), Vector2.ONE, true) == Vector2.ZERO, "invalid direction")
	check(Motion.gaze(Vector2.ONE, Vector2(-1, 2), true) == Vector2.ZERO, "invalid extent")
	var rest := Vector2(4, 2)
	var pivot := Vector2(2, 2)
	var delta := Vector2(1, -1)
	check(Motion.deform_point(rest, 1, Vector2.ZERO, pivot, PI / 2, Vector2(0, 1)).is_equal_approx(Vector2(2, 4)), "rotation around elbow, not translation")
	check(Motion.deform_point(pivot, 1, Vector2.ZERO, pivot, PI / 2, Vector2(0, 1)) == pivot, "stationary pivot")
	check(Motion.deform_point(rest, 1, delta, pivot, 0, Vector2(1, 0)) == rest + delta, "breathing displacement")
	check(Motion.deform_point(rest, 1, delta, pivot, 0, Vector2(2, -1)) == rest + delta, "bounded weights")
	check(Motion.deform_point(rest, NAN, delta, pivot, 1, Vector2.ONE) == rest, "invalid deformation")
	for frame in 49:
		var inhale := Motion.breath(float(frame) / 48.0)
		check(Motion.deform_point(rest, inhale, delta, pivot, 0.06, Vector2.ONE, true) == rest, "pinned foot exact at every phase")
		check(Motion.deform_point(rest, inhale, delta, pivot, 0.06, Vector2.ZERO) == rest, "outside mask exact")
		var a := Motion.deform_point(rest, inhale, delta, pivot, 0.06, Vector2(1, 0))
		var b := Motion.deform_point(rest, inhale, delta, pivot, 0.2, Vector2(1, 0))
		check(a == b, "gesture does not change chest-only vertices")
	check(Motion.deform_point(rest, Motion.breath(1), delta, pivot, 0.06, Vector2.ONE) == rest, "deformation closes loop")
	print("PASS: ", checks, " portrait-motion assertions")
	quit()
