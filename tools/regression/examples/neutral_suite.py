"""Original neutral protocol fixture; this is not a game-runtime adapter."""
import json


def main():
    checks = 0
    failures = []
    coverage = {key: set() for key in ("actions", "transitions", "guard_outcomes", "endings", "invariants")}
    state = {"open": False, "opening_count": 0}

    def check(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(message)

    def inspect_gate():
        coverage["actions"].add("inspect_gate")
        return state["open"]

    def open_gate(allowed):
        coverage["actions"].add("open_gate")
        if not allowed:
            coverage["guard_outcomes"].add("open.blocked")
            return False
        coverage["guard_outcomes"].add("open.allowed")
        if not state["open"]:
            state["open"] = True
            state["opening_count"] += 1
            coverage["transitions"].add("closed_to_open")
        return True

    check(not inspect_gate(), "gate must start closed")
    check(not open_gate(False), "closed permission must block opening")
    unchanged = state == {"open": False, "opening_count": 0}
    check(unchanged, "blocked command must preserve state")
    if unchanged:
        coverage["invariants"].add("closed_gate_unchanged")
    check(open_gate(True), "allowed opening must succeed")
    check(inspect_gate(), "opening must update observed state")
    open_gate(True)
    opened_once = state["opening_count"] == 1
    check(opened_once, "repeat opening must not duplicate transition")
    if opened_once:
        coverage["invariants"].add("opened_once")
    if state["open"]:
        coverage["endings"].add("gate_open")
    result = {"schema_version": 1, "suite_id": "neutral_source",
              "scenario_ids": ["closed_gate", "open_gate"], "passed": not failures,
              "failures": failures, "checks": checks,
              "coverage": {key: sorted(values) for key, values in coverage.items()}}
    print("NEUTRAL_RESULT " + json.dumps(result, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
