# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
extends RefCounted
## Original synthetic control-panel fixture. This is consumer code, not a framework.
var mutation := ""
var state: Dictionary = {}

func reset() -> Dictionary:
    state = {"left": false, "right": false, "deferred": false, "confirmed": false,
        "history": [], "options": []}
    _refresh()
    return {"ok": true}

func snapshot() -> Dictionary:
    return state.duplicate(true)

func restore(saved: Dictionary) -> Dictionary:
    state = saved.duplicate(true)
    return {"ok": true}

func step(action: String) -> Dictionary:
    if action not in state.options: return {"ok": true, "accepted": false}
    match action:
        "enable_left": state.left = true
        "enable_right": state.right = true
        "defer": state.deferred = true
        "confirm": state.confirmed = true
    state.history.append(action)
    _refresh()
    return {"ok": true, "accepted": true}

func _refresh() -> void:
    state.options = []
    if state.confirmed: return
    if not state.left: state.options.append("enable_left")
    if not state.right and mutation != "missing_option": state.options.append("enable_right")
    if not state.deferred: state.options.append("defer")
    if state.left and state.right and not (mutation == "defer_lock" and state.deferred):
        state.options.append("confirm")

# Intentionally separate from _refresh/step. Author requirements do not enumerate
# whatever the current implementation happens to support or bless its own output.
static func contract() -> Dictionary:
    return {"name": "neutral_panels", "actions": ["enable_left", "enable_right", "defer", "confirm"],
        "required_goals": ["both_ready", "direct_confirmation", "deferred_confirmation"],
        "max_depth": 4, "max_states": 128}

static func observe(current: Dictionary) -> Dictionary:
    var goals: Array = []
    var violations: Array = []
    if current.left and current.right: goals.append("both_ready")
    if current.confirmed:
        goals.append("deferred_confirmation" if current.deferred else "direct_confirmation")
        if not current.left or not current.right: violations.append("confirmation_requires_both_panels")
    else:
        if not current.left and "enable_left" not in current.options: violations.append("left_option_required")
        if not current.right and "enable_right" not in current.options: violations.append("right_option_required")
        if current.left and current.right and "confirm" not in current.options:
            violations.append("confirmation_remains_available_after_defer")
    return {"goals": goals, "violations": violations}
