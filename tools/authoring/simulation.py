"""Small reference interpreter for the deliberately restricted authoring policy.

It does not replace the Godot runtime or prove unrestricted story semantics.
Copyright (c) 2026 Derek Wang. MIT licensed.
"""
from __future__ import annotations

from copy import deepcopy

from .validation import ValidationError, require, _same, MAX_EXACT_INTEGER


class Simulator:
    def __init__(self, content: dict):
        self.content = deepcopy(content)
        world = content["world"]
        self.rules = {rule["event"]: rule for rule in world["rules"]}
        self.state = {
            "facts": deepcopy(world["initial_facts"]),
            "inventory": deepcopy(world["initial_inventory"]),
            "scene": world["initial_scene"],
            "coins": 0, "rewards": {}, "processed": {},
            "actors": {actor: {"trust": 0, "knowledge": {}, "memory": {}}
                       for actor in world["actors"]},
        }

    def matches(self, conditions: list[dict], state: dict | None = None) -> bool:
        state = self.state if state is None else state
        for c in conditions:
            op = c["op"]
            if op == "fact_eq":
                passed = _same(state["facts"].get(c["key"]), c["value"])
            elif op == "knows":
                passed = _same(state["actors"][c["npc"]]["knowledge"].get(c["key"]), c["value"])
            elif op == "trust_gte":
                passed = state["actors"][c["npc"]]["trust"] >= c["value"]
            elif op == "inventory_gte":
                passed = state["inventory"][c["key"]] >= c["value"]
            elif op == "scene_eq":
                passed = state["scene"] == c["value"]
            else:
                raise ValidationError("unsupported condition: " + op)
            if not passed:
                return False
        return True

    def selected_branch(self, dialogue_id: str) -> dict:
        dialogue = next((d for d in self.content["dialogues"] if d["id"] == dialogue_id), None)
        require(dialogue is not None, "unknown dialogue: " + dialogue_id)
        return next((b for b in dialogue["branches"] if self.matches(b["when"])), dialogue["fallback"])

    def dispatch(self, command: str, action_id: str) -> str:
        require(command in self.rules, "unknown command: " + command)
        if action_id in self.state["processed"]:
            return "duplicate"
        rule = self.rules[command]
        if not self.matches(rule["when"]):
            return "blocked"
        tx = deepcopy(self.state)
        for effect in rule["effects"]:
            op = effect["op"]
            key = effect.get("key")
            if op == "fact":
                tx["facts"][key] = effect["value"]
            elif op == "know":
                tx["actors"][effect["npc"]]["knowledge"][key] = effect["value"]
            elif op == "remember":
                tx["actors"][effect["npc"]]["memory"][key] = effect["value"]
            elif op == "trust":
                next_trust = tx["actors"][effect["npc"]]["trust"] + effect["delta"]
                if not -MAX_EXACT_INTEGER <= next_trust <= MAX_EXACT_INTEGER:
                    return "blocked"
                tx["actors"][effect["npc"]]["trust"] = next_trust
            elif op == "inventory":
                tx["inventory"][key] += effect["delta"]
                if not 0 <= tx["inventory"][key] <= MAX_EXACT_INTEGER:
                    return "blocked"
            elif op == "reward":
                if key not in tx["rewards"]:
                    tx["rewards"][key] = True
                    tx["coins"] += effect["coins"]
                    if tx["coins"] > MAX_EXACT_INTEGER:
                        return "blocked"
            elif op == "scene":
                tx["scene"] = effect["value"]
            else:
                raise ValidationError("unsupported effect: " + op)
        tx["processed"][action_id] = command
        self.state = tx
        return "applied"

    def choose(self, dialogue: str, branch: str, choice: str, action_id: str) -> str:
        # A retried already accepted action has exactly-once semantics.
        if action_id in self.state["processed"]:
            return "duplicate"
        selected = self.selected_branch(dialogue)
        if selected["id"] != branch:
            return "blocked"
        selected_choice = next((c for c in selected["choices"] if c["id"] == choice), None)
        require(selected_choice is not None, "unknown choice: " + choice)
        return self.dispatch(selected_choice["command"], action_id)


def simulate_fixtures(packet: dict, content: dict) -> dict:
    results = []
    covered = set()
    for fixture in packet["fixtures"]:
        simulation = Simulator(content)
        steps = []
        for step in fixture["steps"]:
            actual = simulation.dispatch(step["command"], step["action_id"])
            require(actual == step["expect"],
                    f"fixture {fixture['id']}: {step['command']} expected {step['expect']}, got {actual}")
            steps.append({"command":step["command"], "action_id":step["action_id"], "status":actual})
        selected = {}
        for dialogue_id, branch_id in fixture["expect_dialogues"].items():
            actual = simulation.selected_branch(dialogue_id)["id"]
            require(actual == branch_id,
                    f"fixture {fixture['id']}: {dialogue_id} expected {branch_id}, got {actual}")
            covered.add((dialogue_id, actual))
            selected[dialogue_id] = actual
        for key, expected in fixture["expect_state"].items():
            if isinstance(expected, dict):
                for nested_key, value in expected.items():
                    require(_same(simulation.state[key].get(nested_key), value),
                            f"fixture {fixture['id']}: state mismatch {key}.{nested_key}")
            else:
                require(_same(simulation.state[key], expected), f"fixture {fixture['id']}: state mismatch {key}")
        results.append({"id":fixture["id"], "passed":True, "steps":steps, "selected_branches":selected})
    required = {(d["id"], b["id"]) for d in content["dialogues"]
                for b in d["branches"] + [d["fallback"]]}
    missing = required - covered
    require(not missing, "branch coverage missing: " + ", ".join(f"{d}/{b}" for d,b in sorted(missing)))
    return {"passed":True, "fixtures":results,
            "coverage":{"covered":[f"{d}/{b}" for d,b in sorted(covered)],
                        "covered_count":len(covered), "required_count":len(required)}}
