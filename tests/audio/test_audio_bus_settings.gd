extends SceneTree

const Settings = preload("res://selected.gd")
var checks := 0
var failures: Array[String] = []
const BUSES := ["Master", "Primary", "Secondary"]
const PATH := "user://synthetic-preferences.cfg"

func check(condition: bool, label: String) -> void:
    checks += 1
    if not condition: failures.append(label)

func server_state() -> Array:
    var result: Array = []
    for index in AudioServer.bus_count:
        result.append([AudioServer.get_bus_name(index), AudioServer.get_bus_volume_linear(index), AudioServer.is_bus_mute(index), AudioServer.get_bus_send(index)])
    return result

func _initialize() -> void:
    var levels := {"Master": 0.8, "Primary": 0.6, "Secondary": 0.4, "Other": "retained"}
    var mutes := {"Master": false, "Primary": false, "Secondary": true, "Other": "retained"}
    for value: float in [-1e300, -0.1, 0.0, 0.01, 0.7, 1.0, 1.1, 1e300]:
        check(Settings.set_level("Primary", value, BUSES, levels), "finite setter accepted")
        check(levels.Primary == clampf(value, 0.0, 1.0), "setter clamps")
    var original := levels.duplicate()
    for value: float in [NAN, INF, -INF]:
        check(not Settings.set_level("Primary", value, BUSES, levels), "nonfinite setter rejected")
        check(levels == original, "rejected setter unchanged")
    check(not Settings.set_level("Unknown", 0.5, BUSES, levels), "unknown level rejected")
    check(levels == original, "unknown level leaves caller unchanged")
    check(Settings.set_muted("Primary", true, BUSES, mutes) and mutes.Primary, "mute setter")
    check(Settings.set_muted("Primary", false, BUSES, mutes) and not mutes.Primary, "unmute setter")
    var original_mutes := mutes.duplicate()
    check(not Settings.set_muted("Unknown", true, BUSES, mutes), "unknown mute rejected")
    check(mutes == original_mutes, "unknown mute unchanged")
    for buses: Array in [["Master", "Master"], [""], [1], [true], ["Bad Name"], ["Bad\tName"], ["Bad\nName"], ["Bad[Name"], ["Bad]Name"]]:
        check(not Settings.set_level("Master", 0.5, buses, levels), "invalid bus list setter rejected")
        check(not Settings.set_muted("Master", true, buses, mutes), "invalid bus list mute rejected")
        check(Settings.apply(buses, levels, mutes) == ERR_INVALID_PARAMETER, "invalid list apply rejected")
        check(Settings.save(PATH, buses, levels, mutes) == ERR_INVALID_PARAMETER, "invalid list save rejected")
        check(Settings.load(PATH, buses, levels, mutes) == ERR_INVALID_PARAMETER, "invalid list load rejected")
    check(not Settings.inaudible("Master", "Primary", levels, mutes), "audible preferences")
    check(Settings.inaudible("Master", "Secondary", levels, mutes), "channel mute")
    check(Settings.inaudible("Master", "Primary", levels, {"Master": true}), "master mute")
    check(Settings.inaudible("Master", "Primary", {"Master": 0.0}, {}), "master zero")
    check(Settings.inaudible("Master", "Primary", {"Primary": 0}, {}), "channel zero integer")
    check(Settings.inaudible("Master", "Primary", {"Primary": -1.0}, {}), "negative treated silent")
    check(not Settings.inaudible("Master", "Primary", {}, {}), "missing query state neutral")
    check(not Settings.inaudible("Master", "Primary", {"Master": NAN, "Primary": false}, {"Master": 1, "Primary": "true"}), "invalid query state neutral")
    levels.Primary = 0.35
    AudioServer.bus_count = 4
    AudioServer.set_bus_name(1, "Primary")
    AudioServer.set_bus_name(2, "Secondary")
    AudioServer.set_bus_name(3, "Unselected")
    AudioServer.set_bus_send(2, "Primary")
    AudioServer.set_bus_volume_db(3, -11.0)
    AudioServer.set_bus_mute(3, true)
    var unselected: Array = server_state()[3]
    check(Settings.apply(BUSES, levels, mutes) == OK, "apply selected state")
    for name: String in BUSES:
        var index := AudioServer.get_bus_index(name)
        check(is_equal_approx(AudioServer.get_bus_volume_linear(index), levels[name]), "server linear gain")
        check(AudioServer.is_bus_mute(index) == mutes[name], "server mute")
    check(server_state()[3] == unselected, "unselected bus preserved")
    check(AudioServer.get_bus_send(2) == "Primary", "send unchanged")
    var before_apply := server_state()
    var missing_levels := levels.duplicate()
    var missing_mutes := mutes.duplicate()
    missing_levels.Missing = 0.1
    missing_mutes.Missing = false
    check(Settings.apply(["Master", "Missing"], missing_levels, missing_mutes) == ERR_DOES_NOT_EXIST, "missing server bus reported")
    check(server_state() == before_apply, "missing server bus rejects atomically")
    for value: Variant in [null, true, "0.5", NAN, INF, -INF, [], {}]:
        var invalid := levels.duplicate()
        invalid.Secondary = value
        check(Settings.apply(BUSES, invalid, mutes) == ERR_INVALID_PARAMETER, "invalid state rejected")
        check(server_state() == before_apply, "invalid apply preserves all buses")
        check(Settings.save(PATH, BUSES, invalid, mutes) == ERR_INVALID_PARAMETER, "invalid save rejected")
    for value: Variant in [null, 0, "false", 1.0, [], {}]:
        var invalid := mutes.duplicate()
        invalid.Secondary = value
        check(Settings.apply(BUSES, levels, invalid) == ERR_INVALID_PARAMETER, "nonboolean mute rejected")
        check(server_state() == before_apply, "invalid mute preserves all buses")
    check(Settings.apply([], {}, {}) == OK, "empty selection no-op")
    check(Settings.apply(["Primary"], {"Primary": -1.0}, {"Primary": false}) == OK, "apply clamps negative")
    check(is_equal_approx(AudioServer.get_bus_volume_db(1), -80.0), "zero gain floors at -80 dB")
    check(AudioServer.is_bus_mute(1), "zero level forces server mute without changing preference")
    check(Settings.apply(["Primary"], {"Primary": 2}, {"Primary": true}) == OK, "apply clamps integer")
    check(is_equal_approx(AudioServer.get_bus_volume_linear(1), 1.0), "unity max applied")
    check(AudioServer.is_bus_mute(1), "positive explicitly muted gain stays muted")
    check(Settings.apply(["Primary"], {"Primary": 0.5}, {"Primary": false}) == OK, "return positive unmuted")
    check(not AudioServer.is_bus_mute(1), "positive gain restores unmuted server")
    check(Settings.apply(["Primary"], {"Primary": 0.000001}, {"Primary": false}) == OK, "tiny positive level")
    check(is_equal_approx(AudioServer.get_bus_volume_db(1), -80.0) and not AudioServer.is_bus_mute(1), "tiny positive level floors without hard mute")
    # Exercise the accepted section-name character space through real persistence.
    var names: Array[String] = ["Mixed_Name-2", "名前", "Étage"]
    for codepoint in range(33, 127):
        var character := String.chr(codepoint)
        if character in ["[", "]"]: continue
        names.append("Key" + character + "Name")
    for name: String in names:
        check(Settings.save(PATH, [name], {name: 0.375}, {name: true}) == OK, "accepted name saves")
        var loaded_levels := {name: 1.0}
        var loaded_mutes := {name: false}
        check(Settings.load(PATH, [name], loaded_levels, loaded_mutes) == OK, "accepted name loads")
        check(loaded_levels[name] == 0.375 and loaded_mutes[name], "punctuation and unicode roundtrip unchanged")
    # Independently authored legacy-format bytes. No schema or reshaping required.
    var legacy := ConfigFile.new()
    for name: String in BUSES:
        legacy.set_value(name, "level", levels[name])
        legacy.set_value(name, "muted", mutes[name])
    var caller_levels := levels.duplicate()
    var caller_mutes := mutes.duplicate()
    check(Settings.save(PATH, BUSES, levels, mutes) == OK, "save preferences")
    check(FileAccess.get_file_as_string(PATH) == legacy.encode_to_text(), "byte-compatible bus-section format")
    check(not FileAccess.file_exists(PATH + ".tmp"), "successful atomic rename leaves no temp")
    check(levels == caller_levels and mutes == caller_mutes, "save does not mutate caller")
    var saved_bytes := FileAccess.get_file_as_bytes(PATH)
    check(Settings.save(PATH, BUSES, levels, mutes) == OK, "overwrite existing preferences")
    check(FileAccess.get_file_as_bytes(PATH) == saved_bytes, "repeat save identical bytes")
    var restored_levels := {"Master": 1.0, "Primary": 1.0, "Secondary": 1.0, "Later": 0.25, "Other": "untouched"}
    var restored_mutes := {"Master": true, "Primary": true, "Secondary": false, "Later": false, "Other": 9}
    var expanded := BUSES + ["Later"]
    check(Settings.load(PATH, expanded, restored_levels, restored_mutes) == OK, "load legacy and newly introduced bus")
    for name: String in BUSES:
        check(restored_levels[name] == levels[name] and restored_mutes[name] == mutes[name], "roundtrip selected preferences")
    check(restored_levels.Later == 0.25 and restored_mutes.Later == false, "missing later section retains defaults")
    check(restored_levels.Other == "untouched" and restored_mutes.Other == 9, "unselected state retained")
    var fixture := ConfigFile.new()
    fixture.set_value("Master", "level", 2)
    fixture.set_value("Primary", "level", -0.5)
    fixture.set_value("Primary", "muted", true)
    fixture.set_value("Secondary", "level", "0.2")
    fixture.set_value("Secondary", "muted", 1)
    fixture.set_value("Unknown", "level", 0.0)
    check(fixture.save(PATH) == OK, "write mixed fixture")
    check(Settings.load(PATH, BUSES, restored_levels, restored_mutes) == OK, "load mixed values")
    check(restored_levels.Master == 1.0 and restored_levels.Primary == 0.0, "load numeric values clamped")
    check(restored_mutes.Master == false and restored_mutes.Primary == true, "missing mute retained and bool merged")
    check(restored_levels.Secondary == levels.Secondary and restored_mutes.Secondary == mutes.Secondary, "invalid types retain defaults")
    check(not restored_levels.has("Unknown") and not restored_mutes.has("Unknown"), "unknown sections ignored")
    for value: Variant in [true, "0", NAN, INF, -INF, [], {}]:
        fixture.set_value("Primary", "level", value)
        check(fixture.save(PATH) == OK, "write invalid level fixture")
        restored_levels.Primary = 0.42
        check(Settings.load(PATH, ["Primary"], restored_levels, restored_mutes) == OK, "parse invalid level variant")
        check(restored_levels.Primary == 0.42, "invalid persisted level skipped")
    var before_levels := restored_levels.duplicate()
    var before_mutes := restored_mutes.duplicate()
    check(Settings.load("user://absent.cfg", BUSES, restored_levels, restored_mutes) == ERR_FILE_NOT_FOUND, "missing file error returned")
    check(restored_levels == before_levels and restored_mutes == before_mutes, "missing file retains defaults")
    var malformed := FileAccess.open(PATH, FileAccess.WRITE)
    malformed.store_string("[Master]\nlevel=0.1\n[broken\n")
    malformed.close()
    var printing_errors := Engine.print_error_messages
    Engine.print_error_messages = false # ConfigFile deliberately logs this tested parse error.
    var parse_error: Error = Settings.load(PATH, BUSES, restored_levels, restored_mutes)
    Engine.print_error_messages = printing_errors
    check(parse_error == ERR_PARSE_ERROR, "whole-file parse error returned")
    check(restored_levels == before_levels and restored_mutes == before_mutes, "parse error merges nothing")
    for path: String in ["", "user://", "user://directory/"]:
        check(Settings.save(path, BUSES, levels, mutes) == ERR_INVALID_PARAMETER, "invalid save path rejected")
        check(Settings.load(path, BUSES, levels, mutes) == ERR_INVALID_PARAMETER, "invalid load path rejected")
    check(Settings.save("user://nonexistent/target.cfg", BUSES, levels, mutes) != OK, "missing parent save error")
    check(Settings.save(PATH, BUSES, levels, mutes) == OK, "restore valid existing preferences")
    saved_bytes = FileAccess.get_file_as_bytes(PATH)
    var bad_levels := levels.duplicate()
    bad_levels.Master = NAN
    check(Settings.save(PATH, BUSES, bad_levels, mutes) == ERR_INVALID_PARAMETER, "invalid overwrite rejected")
    check(FileAccess.get_file_as_bytes(PATH) == saved_bytes, "invalid overwrite preserves original bytes")
    # Block the temp writer: old destination survives a failed write.
    check(DirAccess.make_dir_absolute(PATH + ".tmp") == OK, "make temp obstruction")
    check(Settings.save(PATH, BUSES, levels, mutes) != OK, "temp save error propagated")
    check(FileAccess.get_file_as_bytes(PATH) == saved_bytes, "failed temp write preserves target")
    check(DirAccess.remove_absolute(PATH + ".tmp") == OK, "remove temp obstruction")
    # Target is a directory: rename fails; temp file must be cleaned.
    check(DirAccess.make_dir_absolute("user://target-directory") == OK, "make rename obstruction")
    check(Settings.save("user://target-directory", BUSES, levels, mutes) != OK, "rename error propagated")
    check(DirAccess.dir_exists_absolute("user://target-directory"), "failed rename preserves target directory")
    check(not FileAccess.file_exists("user://target-directory.tmp"), "failed rename cleans temp")
    DirAccess.remove_absolute("user://target-directory")
    DirAccess.remove_absolute(PATH)
    AudioServer.bus_count = 1
    print("Audio settings: %d checks, %d failures" % [checks, failures.size()])
    for failure in failures: printerr(failure)
    quit(0 if failures.is_empty() else 1)
