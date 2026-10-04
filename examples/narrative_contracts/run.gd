# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
extends SceneTree
const Explorer = preload("res://narrative_contract.gd")

func _initialize() -> void:
    call_deferred("run")

func run() -> void:
    var arguments := OS.get_cmdline_user_args()
    var kernel := "--kernel" in arguments
    var script := load("res://kernel_adapter.gd" if kernel else "res://neutral_adapter.gd")
    var adapter = script.new()
    if kernel: root.add_child(adapter)
    if "--mutation" in arguments:
        adapter.mutation = arguments[arguments.find("--mutation") + 1]
    var kernel_rejection_preserved := true
    var reverse_order_rejected := true
    if kernel:
        adapter.reset()
        var before: Dictionary = adapter.snapshot()
        var rejected: Dictionary = adapter.step("publish")
        var after: Dictionary = adapter.snapshot()
        kernel_rejection_preserved = rejected.ok and not rejected.accepted and before.world == after.world
        adapter.reset()
        for action: String in ["prepare", "publish", "defer"]:
            adapter.step(action)
        reverse_order_rejected = "deferred_then_published_at_cutoff" not in adapter.observe(adapter.snapshot()).goals
    var report := Explorer.explore(adapter.contract(), adapter.reset, adapter.snapshot,
        adapter.restore, adapter.step, adapter.observe)
    if kernel:
        report["rejected_kernel_state_unchanged"] = kernel_rejection_preserved
        report["label_attached_to_tree"] = adapter.label.is_inside_tree()
        report["reverse_order_does_not_satisfy_goal"] = reverse_order_rejected
        if not kernel_rejection_preserved or not reverse_order_rejected or not adapter.label.is_inside_tree():
            report["passed"] = false
    var failures: Array = []
    if not report.passed:
        failures.append(report.get("error", report.status))
    print("NARRATIVE_RESULT " + JSON.stringify({"schema_version": 1, "suite_id": "narrative_example",
        "scenario_ids": ["kernel_contract" if kernel else "neutral_contract"],
        "passed": report.passed, "failures": failures, "checks": report.get("observations", 0), "details": report}))
    if kernel: adapter.free()
    quit(0 if report.passed else 1)
