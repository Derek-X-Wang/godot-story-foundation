# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang

extends RefCounted
## Authoritative NPC state. Content never owns these mutable records.
var trust: int = 0
var knowledge: Dictionary = {}
var memory: Dictionary = {}
func pack() -> Dictionary:
	return {"trust": trust, "knowledge": knowledge.duplicate(true), "memory": memory.duplicate(true)}
func unpack(data: Dictionary) -> void:
	trust = int(data.get("trust", 0))
	knowledge = data.get("knowledge", {}).duplicate(true)
	memory = data.get("memory", {}).duplicate(true)
