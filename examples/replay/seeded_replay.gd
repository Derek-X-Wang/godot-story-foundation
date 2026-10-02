# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
extends SceneTree
## Neutral synthetic inventory transfer. This is intentionally a faulty game adapter.
## Prepare/run with scripts/test_replay.py. No story runtime or addons are installed.

const Replay = preload("res://replay_record.gd")
const SEED := 73491
const FAULT_STEP := 6
var state: Dictionary = {}

func _initialize() -> void:
    var arguments := OS.get_cmdline_user_args()
    if arguments.size() != 2 or arguments[0] not in ["--capture", "--replay"]:
        printerr("Use -- --capture PATH or -- --replay PATH")
        quit(2)
        return
    var identity := {
        "tool": FileAccess.get_sha256("res://replay_record.gd"),
        "content": "synthetic-transfer:initial-stock=100:take=1..4:fault-turn=7".sha256_text(),
        "build": FileAccess.get_sha256("res://seeded_replay.gd"),
        "engine": str(Engine.get_version_info()).sha256_text(),
        "versions": {"tool": "semantic-replay/1", "fixture": "synthetic-transfer/1",
            "engine": Engine.get_version_info().string},
    }
    if arguments[0] == "--capture":
        capture(identity, arguments[1])
    else:
        replay(identity, arguments[1])

func capture(identity: Dictionary, destination: String) -> void:
    reset_adapter(SEED, {"turn": 0, "stock": 100, "collected": 0})
    var started: Dictionary = Replay.begin(identity, SEED, snapshot())
    if not started.ok: fail(started); return
    var record: Dictionary = started.record
    var rng := RandomNumberGenerator.new()
    rng.seed = SEED
    for _index in 12:
        var action_id := "transfer"
        var action := {"kind": "transfer", "amount": rng.randi_range(1, 4)}
        var before := snapshot()
        var applied := apply_adapter(action_id, action)
        if not applied.ok: fail(applied); return
        var expectation := check_adapter(action_id, action)
        var appended: Dictionary = Replay.append_step(record, action_id, action, before, snapshot(), expectation)
        if not appended.ok: fail(appended); return
        if not expectation.ok: break
    var validated: Dictionary = Replay.validate(record, identity)
    if not validated.ok or validated.failure_step != FAULT_STEP:
        fail({"error": "capture did not find the deliberate fault at the expected step"}); return
    var output := FileAccess.open(destination, FileAccess.WRITE)
    if output == null: fail({"error": "cannot open replay output"}); return
    output.store_string(Replay.canonical(record).json + "\n")
    output.close()
    print("Replay example captured seed=%d steps=%d expectation_failure_step=%d" % [SEED, record.steps.size(), FAULT_STEP])
    quit(0)

func replay(identity: Dictionary, source: String) -> void:
    var input := FileAccess.open(source, FileAccess.READ)
    if input == null: fail({"error": "cannot open replay input"}); return
    var parser := JSON.new()
    var error := parser.parse(input.get_as_text())
    input.close()
    if error != OK or not parser.data is Dictionary: fail({"error": "invalid replay JSON"}); return
    var result: Dictionary = Replay.verify(parser.data, identity, reset_adapter, apply_adapter, snapshot, check_adapter)
    if not result.ok or not result.expectation_failed or result.failure_step != FAULT_STEP:
        fail(result); return
    print("Replay example reproduced seed=%d steps=%d expectation_failure_step=%d" % [SEED, result.steps, result.failure_step])
    quit(0)

func reset_adapter(_seed_value: int, initial_state: Dictionary) -> Dictionary:
    state = initial_state.duplicate(true)
    return {"ok": true}

func snapshot() -> Dictionary:
    return state.duplicate(true)

func apply_adapter(_action_id: String, action: Dictionary) -> Dictionary:
    if action.get("kind") != "transfer" or not action.get("amount") is float and not action.get("amount") is int:
        return {"ok": false, "error": "unknown synthetic action"}
    var amount := int(action.amount)
    state.turn += 1
    state.stock -= amount
    state.collected += amount
    # Deliberate synthetic fault; never presented as a real game regression.
    if state.turn == FAULT_STEP + 1: state.collected += amount
    return {"ok": true}

func check_adapter(_action_id: String, _action: Dictionary) -> Dictionary:
    return {"ok": state.stock + state.collected == 100,
        "id": "conservation", "expected": 100, "actual": state.stock + state.collected}

func fail(result: Dictionary) -> void:
    printerr("Replay example failed: " + str(result))
    quit(1)
