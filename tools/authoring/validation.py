"""Fail-closed JSON Schema subset and project-specific reference validation.

No executable expressions, external schema resolution, plugins, or model SDKs.
Copyright (c) 2026 Derek Wang. MIT licensed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas"
MAX_EXACT_INTEGER = 2**53 - 1
ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ValidationError(ValueError):
    """An input is invalid, unsafe, stale, or does not meet its contract."""


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValidationError(message)


def validate_exact_integers(value: Any, path: str = "$") -> None:
    """Godot JSON uses IEEE-754 numbers; reject silently rounded integers."""
    if type(value) is int:
        require(-MAX_EXACT_INTEGER <= value <= MAX_EXACT_INTEGER,
                f"{path}: integer is outside the exact JSON/Godot range")
    elif isinstance(value, dict):
        for key, child in value.items():
            validate_exact_integers(child, path + "." + str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_exact_integers(child, f"{path}[{index}]")


def _same(a: Any, b: Any) -> bool:
    return type(a) is type(b) and a == b


def _type(value: Any, name: str) -> bool:
    return {
        "object": lambda: isinstance(value, dict),
        "array": lambda: isinstance(value, list),
        "string": lambda: isinstance(value, str),
        "integer": lambda: type(value) is int,
        "boolean": lambda: type(value) is bool,
        "null": lambda: value is None,
    }[name]()


def validate_schema(value: Any, name: str) -> None:
    """Validate every keyword used by the bundled closed JSON Schemas.

    This is intentionally not a general-purpose JSON Schema implementation.
    External/remote references are never fetched.
    """
    validate_exact_integers(value)
    documents = {p.name: json.loads(p.read_text(encoding="utf-8"))
                 for p in SCHEMA_ROOT.glob("*.schema.json")}
    require(name in documents, f"unknown schema: {name}")

    def walk(v: Any, s: dict, doc: dict, path: str) -> None:
        if "$ref" in s:
            filename, _, fragment = s["$ref"].partition("#")
            target_doc = documents.get(filename) if filename else doc
            require(target_doc is not None, f"{path}: unsupported schema reference")
            target = target_doc
            for part in fragment.strip("/").split("/") if fragment else []:
                target = target[part.replace("~1", "/").replace("~0", "~")]
            walk(v, target, target_doc, path)
            return
        if "oneOf" in s:
            passed = 0
            for candidate in s["oneOf"]:
                try:
                    walk(v, candidate, doc, path)
                    passed += 1
                except ValidationError:
                    pass
            require(passed == 1, f"{path}: unsupported operation or invalid operation fields")
        if "type" in s:
            types = s["type"] if isinstance(s["type"], list) else [s["type"]]
            require(any(_type(v, t) for t in types), f"{path}: expected {'/'.join(types)}")
        if "const" in s:
            require(_same(v, s["const"]), f"{path}: expected constant {s['const']!r}")
        if "enum" in s:
            require(any(_same(v, x) for x in s["enum"]), f"{path}: unsupported value {v!r}")
        if isinstance(v, dict):
            for key in s.get("required", []):
                require(key in v, f"{path}: missing {key}")
            props = s.get("properties", {})
            for key, item in v.items():
                if "propertyNames" in s:
                    walk(key, s["propertyNames"], doc, path + ".<key>")
                if key in props:
                    walk(item, props[key], doc, path + "." + key)
                else:
                    additional = s.get("additionalProperties", True)
                    require(additional is not False, f"{path}: unknown field {key}")
                    if isinstance(additional, dict):
                        walk(item, additional, doc, path + "." + key)
        if isinstance(v, list):
            require(len(v) >= s.get("minItems", 0), f"{path}: missing required branches/items")
            require(len(v) <= s.get("maxItems", 1000000), f"{path}: too many items")
            if s.get("uniqueItems"):
                keys = [json.dumps(x, sort_keys=True, ensure_ascii=False) for x in v]
                require(len(keys) == len(set(keys)), f"{path}: duplicate items")
            if "items" in s:
                for i, item in enumerate(v):
                    walk(item, s["items"], doc, f"{path}[{i}]")
        if isinstance(v, str):
            require(len(v) >= s.get("minLength", 0), f"{path}: empty text")
            require(len(v) <= s.get("maxLength", 1000000), f"{path}: text too long")
            if "pattern" in s:
                require(re.fullmatch(s["pattern"], v) is not None, f"{path}: invalid identifier")
        if type(v) is int:
            require(v >= s.get("minimum", v), f"{path}: below minimum")
            require(v <= s.get("maximum", v), f"{path}: above maximum")

    walk(value, documents[name], documents[name], "$")


def _unique(items: list[dict], label: str) -> None:
    ids = [x["id"] for x in items]
    require(len(ids) == len(set(ids)), f"duplicate {label} IDs")


def safe_prose(text: str) -> None:
    """Plain single-line text only; never emit provider-authored DM syntax."""
    require(not any(ord(c) < 32 or ord(c) == 127 or c in "\x85\u2028\u2029" for c in text),
            "prose must be a single line without control characters")
    require(not any(c in text for c in "[]{}\\<>#|"),
            "prose contains reserved Dialogue Manager markup")
    require(text.strip() == text and bool(text.strip()), "prose has empty or edge whitespace")


def validate_packet(packet: dict) -> None:
    validate_schema(packet, "packet.schema.json")
    reg = packet["registry"]
    world = packet["world"]
    require(set(world["actors"]) == set(reg["actors"]), "world actors must match registry")
    require(set(world["initial_facts"]) == set(reg["facts"]), "world facts must match registry")
    require(set(world["initial_inventory"]) == set(reg["items"]), "world items must match registry")
    require(world["initial_scene"] in reg["scenes"], "unknown initial scene")
    require(packet["scene_card"]["location"] in reg["scenes"], "unknown scene-card location")
    require(bool(packet["scene_card"]["required_dialogues"]), "scene card needs required dialogues")
    persona_actors = [p["actor"] for p in packet["personas"]]
    require(len(persona_actors) == len(set(persona_actors)), "duplicate persona actors")
    require(all(a in reg["actors"] for a in persona_actors), "unknown persona actor")
    _unique(world["rules"], "rule")
    events = [r["event"] for r in world["rules"]]
    require(len(events) == len(set(events)), "each command must have exactly one authoritative rule")
    require(set(events) == set(reg["commands"]), "rule events must match registered commands")
    for key, value in world["initial_facts"].items():
        require(not isinstance(value, str) or not value.startswith("$"),
                f"fact {key}: event interpolation is forbidden")
    for rule in world["rules"]:
        for condition in rule["when"]:
            _condition(condition, packet)
        for effect in rule["effects"]:
            _effect(effect, packet)
        # Guard the full debit, even if more than one effect consumes an item.
        for item in reg["items"]:
            debit = -sum(min(e["delta"], 0) for e in rule["effects"]
                         if e["op"] == "inventory" and e["key"] == item)
            if debit:
                require(any(c["op"] == "inventory_gte" and c["key"] == item and c["value"] >= debit
                            for c in rule["when"]), f"rule {rule['id']}: unguarded inventory debit")
    _unique(packet["fixtures"], "fixture")
    for fixture in packet["fixtures"]:
        for step in fixture["steps"]:
            require(step["command"] in reg["commands"], "fixture references unknown command")
        for dialogue, branch in fixture["expect_dialogues"].items():
            expected = packet["scene_card"]["required_dialogues"]
            require(dialogue in expected and branch in expected[dialogue], "fixture references unknown dialogue/branch")
        expectation = fixture["expect_state"]
        for key, val in expectation.get("facts", {}).items():
            _fact_value(key, val, packet)
        for key in expectation.get("inventory", {}):
            require(key in reg["items"], "fixture references unknown inventory item")
        if "scene" in expectation:
            require(expectation["scene"] in reg["scenes"], "fixture references unknown scene")


def _fact_value(key: str, value: Any, packet: dict) -> None:
    facts = packet["world"]["initial_facts"]
    require(key in packet["registry"]["facts"], f"unknown fact: {key}")
    require(type(value) is type(facts[key]), f"fact {key}: value has wrong type")
    require(not isinstance(value, str) or not value.startswith("$"), "event interpolation is forbidden")


def _condition(c: dict, packet: dict) -> None:
    reg = packet["registry"]
    op = c["op"]
    if "npc" in c:
        require(c["npc"] in reg["actors"], f"unknown actor: {c['npc']}")
    if op in ("fact_eq", "knows"):
        _fact_value(c["key"], c["value"], packet)
    elif op == "inventory_gte":
        require(c["key"] in reg["items"], f"unknown item: {c['key']}")
    elif op == "scene_eq":
        require(c["value"] in reg["scenes"], f"unknown scene: {c['value']}")


def _effect(e: dict, packet: dict) -> None:
    reg = packet["registry"]
    op = e["op"]
    if "npc" in e:
        require(e["npc"] in reg["actors"], f"unknown actor: {e['npc']}")
    if op in ("fact", "know"):
        _fact_value(e["key"], e["value"], packet)
    elif op == "inventory":
        require(e["key"] in reg["items"], f"unknown item: {e['key']}")
    elif op == "remember":
        require(e["key"] in reg["memories"], f"unknown memory: {e['key']}")
        require(not isinstance(e["value"], str) or not e["value"].startswith("$"), "event interpolation is forbidden")
    elif op == "reward":
        require(e["key"] in reg["rewards"], f"unknown reward: {e['key']}")
    elif op == "scene":
        require(e["value"] in reg["scenes"], f"unknown scene: {e['value']}")


def validate_content(packet: dict, content: dict) -> None:
    validate_packet(packet)
    validate_schema(content, "content.schema.json")
    require(content["content_id"] == packet["content_id"], "content ID differs from packet")
    require(content["content_version"] == packet["content_version"], "content version differs from packet")
    require(json.dumps(content["world"], sort_keys=True) == json.dumps(packet["world"], sort_keys=True),
            "candidate changed authoritative world policy")
    _unique(content["dialogues"], "dialogue")
    requirements = packet["scene_card"]["required_dialogues"]
    require(set(requirements) == {d["id"] for d in content["dialogues"]}, "missing or unexpected dialogues")
    for dialogue in content["dialogues"]:
        require(dialogue["speaker"] in packet["registry"]["actors"], "unknown dialogue speaker")
        require(not dialogue["speaker"].startswith(("else", "elif")),
                "speaker ID uses a reserved Dialogue Manager condition prefix")
        require(dialogue["speaker"] in {p["actor"] for p in packet["personas"]}, "speaker needs packet persona")
        branches = dialogue["branches"] + [dialogue["fallback"]]
        _unique(branches, "branch")
        require(set(requirements[dialogue["id"]]) == {b["id"] for b in branches},
                f"{dialogue['id']}: missing or unexpected required branches")
        for branch in branches:
            safe_prose(branch["text"])
            for condition in branch.get("when", []):
                _condition(condition, packet)
            claims = [(x["fact"], json.dumps(x["value"])) for x in branch["claims"]]
            require(len(claims) == len(set(claims)), "duplicate claim annotations")
            for claim in branch["claims"]:
                _fact_value(claim["fact"], claim["value"], packet)
                truth = {"op":"fact_eq", "key":claim["fact"], "value":claim["value"]}
                knowledge = {"op":"knows", "npc":dialogue["speaker"], "key":claim["fact"], "value":claim["value"]}
                require(truth in branch.get("when", []) and knowledge in branch.get("when", []),
                        f"{dialogue['id']}/{branch['id']}: claim requires matching world-truth and speaker-knowledge guards")
            _unique(branch["choices"], "choice")
            for choice in branch["choices"]:
                safe_prose(choice["text"])
                require(":" not in choice["text"],
                        "choice text cannot contain a colon in the v0.1 plain-text subset")
                require(choice["command"] in packet["registry"]["commands"], "choice references unknown command")
