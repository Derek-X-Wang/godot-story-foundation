extends RefCounted
## Optional stateless portrait motion math, in consumer-owned local coordinates.
## No assets, clock, scene transforms, face segmentation or automatic rigging.

static func breath(cycle: float) -> float:
	if not is_finite(cycle):
		return 0.0
	return 0.5 - 0.5 * cos(TAU * fposmod(cycle, 1.0))

## One scheduled blink, not a scheduler. Missing authored eyelid support stays open.
static func blink(elapsed: float, duration: float, has_eyelid_layer: bool) -> float:
	if not has_eyelid_layer or not is_finite(elapsed) or not is_finite(duration):
		return 0.0
	if duration <= 0.0 or elapsed <= 0.0 or elapsed >= duration:
		return 0.0
	return sin(PI * elapsed / duration)

## Only move an independently authored iris layer, never the whole painted eye.
static func gaze(direction: Vector2, extent: Vector2, has_iris_layer: bool) -> Vector2:
	if not has_iris_layer or not direction.is_finite() or not extent.is_finite():
		return Vector2.ZERO
	if extent.x < 0.0 or extent.y < 0.0:
		return Vector2.ZERO
	return direction.clamp(Vector2(-1, -1), Vector2.ONE) * extent

## Compose local breathing displacement with a small rest-space pivot gesture.
## Always sample from the rest point, not last frame's result (no accumulating drift).
## Weights are authored per vertex; pin overrides both channels exactly.
## The caller owns masks, pivot, direction, amplitudes and their visual review.
static func deform_point(rest: Vector2, inhale: float, displacement: Vector2,
		pivot: Vector2, angle_radians: float, weights: Vector2, pinned: bool = false) -> Vector2:
	if pinned or not rest.is_finite() or not is_finite(inhale):
		return rest
	if not displacement.is_finite() or not pivot.is_finite() or not is_finite(angle_radians) or not weights.is_finite():
		return rest
	var phase := clampf(inhale, 0.0, 1.0)
	var influence := weights.clamp(Vector2.ZERO, Vector2.ONE)
	var arm := rest - pivot
	return rest + phase * influence.x * displacement + influence.y * (arm.rotated(angle_radians * phase) - arm)
