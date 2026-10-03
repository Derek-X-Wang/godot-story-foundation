# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
extends RefCounted
## Independently optional bus creation. No player, asset, state or autoload ownership.

## Return an existing bus untouched, or append a new bus routed to an existing send.
## Appending through bus_count avoids the Godot 4.6.3 Web add_bus(-1) graph path.
## Return -1 for an empty name or an absent send when creating a bus.
static func ensure_bus(bus_name: String, send: String = "Master") -> int:
    if bus_name.is_empty(): return -1
    var existing := AudioServer.get_bus_index(bus_name)
    if existing >= 0: return existing
    if AudioServer.get_bus_index(send) < 0: return -1
    var index := AudioServer.bus_count
    AudioServer.bus_count = index + 1
    AudioServer.set_bus_name(index, bus_name)
    AudioServer.set_bus_send(index, send)
    return index
