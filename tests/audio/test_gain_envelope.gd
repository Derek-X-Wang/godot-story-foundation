extends SceneTree

const Envelope = preload("res://selected.gd")
var checks := 0
var failures: Array[String] = []

func check(condition: bool, label: String) -> void:
    checks += 1
    if not condition: failures.append(label)

func _initialize() -> void:
    for endpoints: Array in [[0.0, 1.0], [1.0, 0.0], [0.2, 0.85], [-30.0, -4.5], [1.5, 3.0], [0.37, 0.37]]:
        var start: float = endpoints[0]
        var target: float = endpoints[1]
        for duration: float in [0.05, 0.7, 2.0, 9.5]:
            var previous := start
            for index in 101:
                var elapsed := duration * index / 100.0
                var t := clampf(elapsed / duration, 0.0, 1.0)
                var expected := lerpf(start, target, t * t * (3.0 - 2.0 * t))
                var actual: float = Envelope.sample(start, target, elapsed, duration)
                check(actual == expected, "exact native lerpf smoothstep trajectory")
                check(actual >= minf(start, target) - 1e-12 and actual <= maxf(start, target) + 1e-12, "gain within endpoint interval")
                check(actual >= previous - 1e-12 if target >= start else actual <= previous + 1e-12, "monotone trajectory")
                previous = actual
            check(Envelope.sample(start, target, -1.0, duration) == lerpf(start, target, 0.0), "negative elapsed clamps to start")
            check(Envelope.sample(start, target, 0.0, duration) == lerpf(start, target, 0.0), "start endpoint")
            check(Envelope.sample(start, target, duration, duration) == lerpf(start, target, 1.0), "completion endpoint")
            check(Envelope.sample(start, target, duration * 2.0, duration) == lerpf(start, target, 1.0), "overshoot elapsed clamps")
            check(Envelope.sample(start, target, duration / 2.0, duration) == lerpf(start, target, 0.5), "midpoint")
        check(Envelope.sample(start, target, 0.0, 0.0) == target, "zero duration immediate")
        check(Envelope.sample(start, target, -1.0, -1.0) == target, "negative duration immediate")
    # Interruptions/reversal remain game-owned: capture sampled gain as the next start.
    var interrupted: float = Envelope.sample(0.0, 1.0, 0.4, 1.0)
    check(Envelope.sample(interrupted, 0.0, 0.0, 0.3) == interrupted, "retarget begins continuously")
    check(is_equal_approx(Envelope.sample(interrupted, 0.0, 0.15, 0.3), interrupted / 2.0), "retarget midpoint")
    check(Envelope.sample(interrupted, 0.0, 0.3, 0.3) == 0.0, "retarget completion")
    print("Audio envelope: %d checks, %d failures" % [checks, failures.size()])
    for failure in failures: printerr(failure)
    quit(0 if failures.is_empty() else 1)
