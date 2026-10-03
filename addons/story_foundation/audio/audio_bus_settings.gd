# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
extends RefCounted
## Caller-owned bus preferences and explicit-path ConfigFile persistence.
## No default buses, file path, player, assets, autoload or module dependencies.

static func set_level(bus_name: String, value: float, buses: Array, levels: Dictionary) -> bool:
    if not _valid_buses(buses) or not bus_name in buses or not is_finite(value): return false
    levels[bus_name] = clampf(value, 0.0, 1.0)
    return true

static func set_muted(bus_name: String, value: bool, buses: Array, mutes: Dictionary) -> bool:
    if not _valid_buses(buses) or not bus_name in buses: return false
    mutes[bus_name] = value
    return true

## Preference-only query, not a measurement of the AudioServer graph or output device.
## Absent/invalid entries mean unity gain and unmuted; consumer supplies its defaults.
static func inaudible(master_bus: String, bus_name: String, levels: Dictionary, mutes: Dictionary) -> bool:
    for name: String in [master_bus, bus_name]:
        var muted: Variant = mutes.get(name, false)
        if muted is bool and muted: return true
        var level: Variant = levels.get(name, 1.0)
        if _finite_number(level) and float(level) <= 0.0: return true
    return false

## Validate all selected state and bus indexes before changing any AudioServer value.
## Callers create their own buses; this never changes names, sends, effects or ordering.
static func apply(buses: Array, levels: Dictionary, mutes: Dictionary) -> Error:
    if not _valid_state(buses, levels, mutes): return ERR_INVALID_PARAMETER
    var indexes: Array[int] = []
    for bus_name: String in buses:
        var index := AudioServer.get_bus_index(bus_name)
        if index < 0: return ERR_DOES_NOT_EXIST
        indexes.append(index)
    for position in buses.size():
        var bus_name: String = buses[position]
        var level := clampf(float(levels[bus_name]), 0.0, 1.0)
        AudioServer.set_bus_volume_db(indexes[position], linear_to_db(maxf(level, 0.0001)))
        AudioServer.set_bus_mute(indexes[position], mutes[bus_name] or level == 0.0)
    return OK

## Write bus-name sections with level/muted keys, then replace the target by rename.
## Single writer only: the caller reserves path + ".tmp". Parent directories must exist.
## Successful Web save requests persistence sync; it is not a durability acknowledgement.
static func save(path: String, buses: Array, levels: Dictionary, mutes: Dictionary) -> Error:
    if not _valid_path(path) or not _valid_state(buses, levels, mutes): return ERR_INVALID_PARAMETER
    var config := ConfigFile.new()
    for bus_name: String in buses:
        config.set_value(bus_name, "level", clampf(float(levels[bus_name]), 0.0, 1.0))
        config.set_value(bus_name, "muted", mutes[bus_name])
    var temporary := path + ".tmp"
    var error := config.save(temporary)
    if error != OK: return error
    error = DirAccess.rename_absolute(ProjectSettings.globalize_path(temporary), ProjectSettings.globalize_path(path))
    if error != OK:
        DirAccess.remove_absolute(ProjectSettings.globalize_path(temporary))
        return error
    if OS.has_feature("web"):
        JavaScriptBridge.force_fs_sync()
    return OK

## Merge only valid selected entries. Missing keys retain caller defaults, including
## newly added buses; unknown sections are ignored. Read/parse errors mutate nothing.
static func load(path: String, buses: Array, levels: Dictionary, mutes: Dictionary) -> Error:
    if not _valid_path(path) or not _valid_buses(buses): return ERR_INVALID_PARAMETER
    var config := ConfigFile.new()
    var error := config.load(path)
    if error != OK: return error
    for bus_name: String in buses:
        if config.has_section_key(bus_name, "level"):
            var level: Variant = config.get_value(bus_name, "level")
            if _finite_number(level): levels[bus_name] = clampf(float(level), 0.0, 1.0)
        if config.has_section_key(bus_name, "muted"):
            var muted: Variant = config.get_value(bus_name, "muted")
            if muted is bool: mutes[bus_name] = muted
    return OK

static func _finite_number(value: Variant) -> bool:
    return (value is int or value is float) and is_finite(float(value))

static func _valid_buses(buses: Array) -> bool:
    var seen: Dictionary = {}
    for name: Variant in buses:
        if not name is String or name.is_empty() or seen.has(name): return false
        # These characters cannot round-trip as ConfigFile section identifiers.
        for character: String in [" ", "\t", "\r", "\n", "[", "]"]:
            if character in name: return false
        seen[name] = true
    return true

static func _valid_state(buses: Array, levels: Dictionary, mutes: Dictionary) -> bool:
    if not _valid_buses(buses): return false
    for bus_name: String in buses:
        if not _finite_number(levels.get(bus_name)) or not mutes.get(bus_name) is bool: return false
    return true

static func _valid_path(path: String) -> bool:
    return not path.is_empty() and not path.ends_with("/") and ProjectSettings.globalize_path(path).is_absolute_path()
