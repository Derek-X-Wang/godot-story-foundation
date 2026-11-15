extends RefCounted
## Experimental independent adapter; no automatic asset extraction.
const Motion = preload("portrait_idle_motion.gd")
static func sample(time: float, extent: Vector2, iris_supported: bool) -> Vector2:
	if not is_finite(time):
		return Vector2.ZERO
	var p := fposmod(time, 8.0)
	# Hold the gaze, then ease to another nearby fixation. Do not oscillate continuously.
	var times := [0.0, 1.8, 2.1, 3.7, 4.0, 5.7, 6.0, 7.7, 8.0]
	var values := [Vector2.ZERO, Vector2.ZERO, Vector2(-0.6, 0.1), Vector2(-0.6, 0.1), Vector2(0.45, -0.1), Vector2(0.45, -0.1), Vector2.ZERO, Vector2.ZERO, Vector2.ZERO]
	for i in range(times.size()-1):
		if p >= times[i] and p <= times[i+1]:
			var u: float = (p-times[i])/(times[i+1]-times[i])
			return Motion.gaze(values[i].lerp(values[i+1], u*u*(3.0-2.0*u)), extent, iris_supported)
	return Vector2.ZERO
