# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
extends RefCounted
## Optional deterministic ordering of game-owned draw records. API version 1.
## Exact ascending ground_y, then tie, then unique String id. No approximate
## equality: an epsilon comparator can violate transitivity and corrupt sorting.

const API_VERSION := 1

## Returns {ok, error, items}. Failure returns no partial output; input is never
## changed. Success deep-copies dictionaries/arrays, preserving arbitrary payload.
## Object/Resource payload references retain normal Godot duplicate semantics.
static func sorted_records(records: Array[Dictionary]) -> Dictionary:
    var items: Array[Dictionary] = []
    var seen := {}
    for index in records.size():
        var record := records[index]
        for key: String in ["ground_y", "tie"]:
            if not record.has(key) or not _finite_number(record[key]):
                return {"ok": false, "error": "record %d requires finite numeric %s" % [index, key], "items": items}
        if not record.has("id") or not record.id is String or record.id.is_empty():
            return {"ok": false, "error": "record %d requires a nonempty String id" % index, "items": items}
        if seen.has(record.id):
            return {"ok": false, "error": "record IDs must be unique", "items": items}
        seen[record.id] = true
    # Validate the complete input first, including duplicates, before copying it.
    for record: Dictionary in records:
        items.append(record.duplicate(true))
    items.sort_custom(_less)
    return {"ok": true, "error": "", "items": items}

static func _finite_number(value: Variant) -> bool:
    return typeof(value) == TYPE_INT or (typeof(value) == TYPE_FLOAT and is_finite(value))

static func _less(a: Dictionary, b: Dictionary) -> bool:
    var depth := _compare_number(a.ground_y, b.ground_y)
    if depth != 0: return depth < 0
    var tie := _compare_number(a.tie, b.tie)
    if tie != 0: return tie < 0
    return a.id < b.id

static func _compare_number(a: Variant, b: Variant) -> int:
    # Avoid mixed int/float rounding near 2^53. Direct mixed comparisons can call
    # different integer keys equal to one float, breaking transitivity as well.
    if typeof(a) == typeof(b):
        return -1 if a < b else (1 if a > b else 0)
    if typeof(a) == TYPE_FLOAT:
        return -_compare_number(b, a)
    # Here a is int64 and b is a finite float64. Guard the conversion boundary.
    if b >= 9223372036854775808.0: return -1
    if b < -9223372036854775808.0: return 1
    var integer := int(b)
    if a < integer: return -1
    if a > integer: return 1
    # Equal integer parts can only differ through b's fractional part, which is
    # representable exactly in this range (large float64 values are integral).
    return -1 if float(a) < b else (1 if float(a) > b else 0)
