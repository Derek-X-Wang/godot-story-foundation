extends SceneTree

const Depth = preload("res://selected.gd")
var checks := 0
var failures: Array[String] = []

func check(condition: bool, label: String) -> void:
    checks += 1
    if not condition: failures.append(label)

func ids(items: Array) -> Array:
    var result: Array = []
    for item: Dictionary in items: result.append(item.id)
    return result

func _initialize() -> void:
    check(Depth.sorted_records([]).ok and Depth.sorted_records([]).items.is_empty(), "empty queue")
    var records: Array[Dictionary] = [
        {"id": "front", "ground_y": 20.0, "tie": -5, "payload": {"tags": ["intact"]}},
        {"id": "z", "ground_y": 10.0, "tie": 0},
        {"id": "a", "ground_y": 10, "tie": 0.0},
        {"id": "first", "ground_y": -5, "tie": 100},
        {"id": "tie", "ground_y": 10.0, "tie": -1},
    ]
    var expected := ["first", "tie", "a", "z", "front"]
    var before := records.duplicate(true)
    var outcome: Dictionary = Depth.sorted_records(records)
    check(outcome.ok and outcome.error == "", "valid records")
    check(ids(outcome.items) == expected, "ground tie id ordering")
    check(records == before, "source queue not mutated")
    check(outcome.items.back().payload.tags == ["intact"], "payload preserved")
    outcome.items.back().payload.tags.append("copy")
    check(records[0].payload.tags == ["intact"], "nested dictionary and array copied")
    for index in 30:
        records.push_back(records.pop_front())
        if index % 2 == 0: records.reverse()
        check(ids(Depth.sorted_records(records).items) == expected, "permutation repeat determinism")
    var close_depths: Array[Dictionary] = [
        {"id": "a", "ground_y": 1.000009, "tie": 0},
        {"id": "z", "ground_y": 1.0, "tie": 0},
        {"id": "m", "ground_y": 1.000004, "tie": 0},
    ]
    check(ids(Depth.sorted_records(close_depths).items) == ["z", "m", "a"], "near depths use exact ordering")
    var large: Array[Dictionary] = [
        {"id": "a", "ground_y": 9007199254740993, "tie": 0},
        {"id": "z", "ground_y": 9007199254740992.0, "tie": 0},
        {"id": "m", "ground_y": 9007199254740992, "tie": 0},
        {"id": "max_int", "ground_y": 9223372036854775807, "tie": 0},
        {"id": "max_float", "ground_y": 9223372036854775808.0, "tie": 0},
        {"id": "min_int", "ground_y": -9223372036854775807 - 1, "tie": 0},
        {"id": "min_float", "ground_y": -9223372036854775808.0, "tie": 0},
        {"id": "below_int", "ground_y": -1e30, "tie": 0},
    ]
    check(ids(Depth.sorted_records(large).items) == ["below_int", "min_float", "min_int", "m", "z", "a", "max_int", "max_float"], "exact mixed numeric extremes")
    var large_ties: Array[Dictionary] = []
    for record: Dictionary in large:
        large_ties.append({"id": record.id, "ground_y": 0.0, "tie": record.ground_y})
    check(ids(Depth.sorted_records(large_ties).items) == ids(Depth.sorted_records(large).items), "secondary sort exact numeric extremes")
    var values: Array = [-1e30, -9223372036854775808.0, -9223372036854775807 - 1, -9007199254740993, -9007199254740992.0, -1.5, -1, -0.5, -0.0, 0, 0.5, 1, 1.5, 9007199254740992.0, 9007199254740993, 9223372036854775807, 9223372036854775808.0, 1e30]
    for a in values:
        for b in values:
            check(Depth._compare_number(a, b) == -Depth._compare_number(b, a), "numeric comparator antisymmetric")
            for c in values:
                if Depth._compare_number(a, b) < 0 and Depth._compare_number(b, c) < 0:
                    check(Depth._compare_number(a, c) < 0, "numeric comparator transitive")
    for value in values:
        check(Depth._compare_number(value, value) == 0, "numeric comparator equality")
    var malformed: Array = [
        {}, {"id": "a", "ground_y": 1}, {"id": "a", "ground_y": 1, "tie": "0"},
        {"id": "a", "ground_y": true, "tie": 0}, {"id": "a", "ground_y": "1", "tie": 0},
        {"id": "a", "ground_y": INF, "tie": 0}, {"id": "a", "ground_y": NAN, "tie": 0},
        {"id": "a", "ground_y": 1, "tie": -INF}, {"id": "a", "ground_y": 1, "tie": NAN},
        {"id": 1, "ground_y": 1, "tie": 0}, {"id": "", "ground_y": 1, "tie": 0},
    ]
    for record: Dictionary in malformed:
        var input: Array[Dictionary] = [{"id": "valid", "ground_y": 0, "tie": 0}, record]
        var original := input.duplicate(true)
        outcome = Depth.sorted_records(input)
        check(not outcome.ok and not outcome.error.is_empty() and outcome.items.is_empty(), "invalid records fail without partial output")
        # NaN is not equal to itself; check non-NaN source fields for mutation.
        check(input.size() == original.size() and input[0] == original[0], "failure leaves input intact")
    var duplicate: Array[Dictionary] = [{"id": "same", "ground_y": 1, "tie": 0}, {"id": "same", "ground_y": 2, "tie": 1}]
    outcome = Depth.sorted_records(duplicate)
    check(not outcome.ok and outcome.items.is_empty(), "duplicate stable IDs rejected")
    if failures.is_empty():
        print("Scene depth: %d checks passed" % checks)
        quit(0)
    else:
        for failure: String in failures: push_error(failure)
        print("Scene depth: %d/%d checks failed" % [failures.size(), checks])
        quit(1)
