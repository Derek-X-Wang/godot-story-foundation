extends SceneTree

const Buses = preload("res://selected.gd")
var checks := 0
var failures: Array[String] = []

func check(condition: bool, label: String) -> void:
    checks += 1
    if not condition: failures.append(label)

func snapshot() -> Array:
    var result: Array = []
    for index in AudioServer.bus_count:
        var effects: Array = []
        for position in AudioServer.get_bus_effect_count(index):
            effects.append([AudioServer.get_bus_effect(index, position), AudioServer.is_bus_effect_enabled(index, position)])
        result.append({"name": AudioServer.get_bus_name(index), "send": AudioServer.get_bus_send(index),
            "volume": AudioServer.get_bus_volume_db(index), "mute": AudioServer.is_bus_mute(index),
            "solo": AudioServer.is_bus_solo(index), "bypass": AudioServer.is_bus_bypassing_effects(index),
            "effects": effects})
    return result

func _initialize() -> void:
    AudioServer.bus_count = 3
    AudioServer.set_bus_name(1, "Primary")
    AudioServer.set_bus_name(2, "Secondary")
    AudioServer.set_bus_send(2, "Primary")
    AudioServer.set_bus_volume_db(0, -3.0)
    AudioServer.set_bus_volume_db(1, -7.0)
    AudioServer.set_bus_mute(1, true)
    AudioServer.set_bus_solo(2, true)
    AudioServer.set_bus_bypass_effects(2, true)
    var effect := AudioEffectAmplify.new()
    effect.volume_db = -4.0
    AudioServer.add_bus_effect(1, effect)
    AudioServer.set_bus_effect_enabled(1, 0, false)
    var original := snapshot()
    check(Buses.ensure_bus("Master") == 0, "existing master returned")
    check(snapshot() == original, "master preserved exactly")
    check(Buses.ensure_bus("Secondary", "Absent") == 2, "existing bus ignores proposed missing send")
    check(snapshot() == original, "existing non-master bus preserved exactly")
    check(Buses.ensure_bus("Primary", "Secondary") == 1, "existing bus does not reroute")
    check(snapshot() == original, "existing effects flags sends and order preserved")
    check(Buses.ensure_bus("") == -1, "empty new name rejected")
    check(Buses.ensure_bus("Unused", "Absent") == -1, "missing send rejected")
    check(Buses.ensure_bus("Self", "Self") == -1, "new self send rejected")
    check(snapshot() == original, "failed requests preserve layout")
    for index in 32:
        var before := snapshot()
        var name := "Channel_%02d" % index
        var send := "Master" if index % 2 == 0 else "Primary"
        var created: int = Buses.ensure_bus(name, send)
        check(created == before.size(), "append index")
        check(AudioServer.bus_count == before.size() + 1, "append exactly once")
        check(AudioServer.get_bus_name(created) == name, "exact new name")
        check(AudioServer.get_bus_send(created) == send, "explicit new send")
        check(snapshot().slice(0, before.size()) == before, "append preserves every prior bus")
        var appended := snapshot()
        check(Buses.ensure_bus(name, "Secondary") == created, "repeat stable index")
        check(snapshot() == appended, "repeat no mutation")
    AudioServer.bus_count = 1
    print("Audio buses: %d checks, %d failures" % [checks, failures.size()])
    for failure in failures: printerr(failure)
    quit(0 if failures.is_empty() else 1)
