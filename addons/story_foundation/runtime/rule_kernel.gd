# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang

extends RefCounted
## Synchronous, transactional story state. Only dispatch and restore commit changes.
const ActorRecord = preload("res://addons/story_foundation/runtime/actor_record.gd")
const MAX_EVENTS: int = 64
## Inclusive integer range exactly representable in JSON's IEEE-754 consumers.
const MAX_SAFE_INTEGER: int = 9007199254740991
var _content: Dictionary = {}
var _state: Dictionary = {}
var _actors: Dictionary = {}
var _rules: Dictionary = {}
var _match_error: String = ""

## Content should be validated before configuration. Input data is copied deeply.
func configure(new_content: Dictionary, population: int = 12) -> void:
	_content = new_content.duplicate(true)
	_rules.clear()
	var sorted_rules: Array = _content.get("rules", []).duplicate(true)
	sorted_rules.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		if int(a.get("priority", 0)) == int(b.get("priority", 0)):
			return str(a.id) < str(b.id)
		return int(a.get("priority", 0)) < int(b.get("priority", 0)))
	for rule: Dictionary in sorted_rules:
		var event_type: String = str(rule.event)
		if not _rules.has(event_type):
			_rules[event_type] = []
		_rules[event_type].append(rule)
	_state = {"schema":2,"content_version":int(_content.get("version",1)),"clock":0,"scene":_initial_scene(),"facts":_content.get("initial_facts",{}).duplicate(true),"inventory":_initial_inventory(),"coins":0,"rewards":{},"timers":[],"queue":[],"processed":{},"next_seq":0,"trace":[]}
	_actors_init(_content, population)

func _initial_scene() -> String:
	return str(_content.get("initial_scene", "village"))

func _initial_inventory() -> Dictionary:
	# Legacy content without an inventory declaration keeps the original defaults.
	return _content.get("initial_inventory", {"herb": 0, "medicine": 0}).duplicate(true)

func _actors_init(data: Dictionary, population: int) -> void:
	_actors.clear()
	for id: String in data.get("actors", []):
		_actors[id] = ActorRecord.new()
	for i: int in range(maxi(0, population - _actors.size())):
		_actors["extra_%05d" % i] = ActorRecord.new()

func _actors_read() -> Dictionary:
	var packed: Dictionary = {}
	for id: String in _actors:
		packed[id] = _actors[id].pack()
	return packed

func _actors_write(actors: Dictionary) -> void:
	for id: String in _actors.keys():
		if not actors.has(id): _actors.erase(id)
	for id: String in actors:
		if not _actors.has(id): _actors[id] = ActorRecord.new()
		_actors[id].unpack(actors[id])

func _actor_read(id: String) -> Variant:
	return _actors[id].pack() if _actors.has(id) else null

func _actors_commit(touched: Dictionary) -> void:
	for id: String in touched:
		_actors[id].unpack(touched[id])

func _touch_actor(tx: Dictionary, id: String) -> bool:
	if tx.actors.has(id): return true
	var actor: Variant = _actor_read(id)
	if actor == null: return false
	tx.actors[id] = actor
	return true

func snapshot() -> Dictionary:
	var result: Dictionary = _state.duplicate(true)
	result.actors = _actors_read()
	return result

## Returns a copy of a world fact, or a copy of the supplied fallback.
func world_fact(key: String, default_value: Variant = null) -> Variant:
	return _copy_value(_state.get("facts", {}).get(key, default_value))

## Returns a copy of an NPC's knowledge. World facts are never a fallback.
func npc_knows(npc: String, key: String, default_value: Variant = null) -> Variant:
	var actor: Variant = _actor_read(npc)
	if actor == null:
		return _copy_value(default_value)
	return _copy_value(actor.knowledge.get(key, default_value))

## Evaluates the same condition language as dispatch, without committing changes.
## A false condition is a successful evaluation; a malformed one has ok=false.
func evaluate_conditions(conditions: Variant, event: Dictionary = {}) -> Dictionary:
	var tx: Dictionary = _state.duplicate(true)
	tx.actors = {}
	var matched: bool = _matches(tx, event.duplicate(true), conditions)
	return {"ok": _match_error.is_empty(), "matched": matched, "error": _match_error}

func _copy_value(value: Variant) -> Variant:
	if value is Dictionary or value is Array:
		return value.duplicate(true)
	return value

func dispatch(action: Dictionary) -> Dictionary:
	return _run_transaction(action)

## A gameplay command must match a rule when its submitted event is processed.
## Unavailable commands do not consume their action IDs. Accepted retries remain
## duplicates even when their original conditions no longer match.
func dispatch_command(action: Dictionary) -> Dictionary:
	return _run_transaction(action, true)

func _valid_action(action: Dictionary) -> bool:
	return action.get("id", null) is String and not action.id.is_empty() and action.get("type", null) is String and not action.type.is_empty()

func _run_transaction(action: Dictionary, require_rule_match: bool = false) -> Dictionary:
	if not _valid_action(action):
		return {"ok":false,"error":"invalid_action","trace":[]}
	if _state.processed.has(action.id):
		return {"ok":true,"duplicate":true,"events_processed":0,"trace":[]}
	if require_rule_match and not _rules.has(action.type):
		return {"ok": false, "error": "unknown_command", "trace": []}
	# Global metadata is copied; actors stage on first touch and commit only on success.
	# Authoritative components never change during validation/queue drain.
	var tx: Dictionary = _state.duplicate(true)
	tx.actors = {}
	var trace: Array = []
	if action.type == "advance":
		var amount = action.get("amount", 1)
		if not _integer(amount) or amount < 0 or amount > 1000:
			return {"ok":false,"error":"invalid_amount","trace":[]}
		var next_clock: int = int(tx.clock) + int(amount)
		if not _integer(next_clock):
			return {"ok": false, "error": "invalid_integer", "trace": []}
		tx.clock = next_clock
		tx.timers.sort_custom(func(a: Dictionary,b: Dictionary)->bool: return a.seq < b.seq if a.due == b.due else a.due < b.due)
		var future: Array = []
		for timer: Dictionary in tx.timers:
			if timer.due <= tx.clock:
				_enqueue(tx, timer.event)
			else:
				future.append(timer)
		tx.timers = future
	# Identify the submitted event independently of restored or emitted events.
	var submitted_seq: int = int(tx.next_seq)
	var submitted_rule_matched: bool = false
	_enqueue(tx, action)
	var count: int = 0
	while not tx.queue.is_empty():
		if count >= MAX_EVENTS:
			trace.append("ABORT:cycle_limit; pending=%d" % tx.queue.size())
			return {"ok":false,"error":"cycle_limit","trace":trace}
		var event: Dictionary = tx.queue.pop_front()
		count += 1
		trace.append("event:%s#%s" % [event.type,event.seq])
		for rule: Dictionary in _rules.get(str(event.type), []):
			if not _matches(tx, event, rule.get("when", [])):
				if not _match_error.is_empty():
					trace.append("ABORT:"+_match_error)
					return {"ok":false,"error":_match_error,"trace":trace}
				continue
			if int(event.seq) == submitted_seq:
				submitted_rule_matched = true
			trace.append("rule:" + str(rule.id))
			for effect: Dictionary in rule.get("effects", []):
				var error: String = _effect(tx, event, effect, trace)
				if not error.is_empty():
					trace.append("ABORT:"+error)
					return {"ok":false,"error":error,"trace":trace}
		if require_rule_match and int(event.seq) == submitted_seq and not submitted_rule_matched:
			return {"ok": false, "error": "command_unavailable", "trace": []}
	# Every committed number must survive a JSON save/load without precision loss.
	if not _all_integral(tx):
		trace.append("ABORT:invalid_integer")
		return {"ok": false, "error": "invalid_integer", "trace": trace}
	var facts_error: String = _validate_declared_facts(tx.facts)
	if not facts_error.is_empty():
		trace.append("ABORT:invalid_fact_type")
		return {"ok": false, "error": "invalid_fact_type", "trace": trace}
	tx.processed[action.id] = true
	tx.trace.append_array(trace)
	if tx.trace.size() > 128:
		tx.trace = tx.trace.slice(tx.trace.size()-128)
	var actors: Dictionary = tx.actors
	tx.erase("actors")
	_state = tx
	_actors_commit(actors)
	return {"ok":true,"duplicate":false,"events_processed":count,"trace":trace}

func _enqueue(tx: Dictionary, event: Dictionary) -> void:
	var item: Dictionary = event.duplicate(true)
	item.seq = tx.next_seq
	tx.next_seq = int(tx.next_seq) + 1
	tx.queue.append(item)

func _value(value: Variant, event: Dictionary) -> Variant:
	if value is String and value.begins_with("$"):
		return event.get(value.substr(1), null)
	return value

func _matches(tx: Dictionary, event: Dictionary, conditions: Variant) -> bool:
	_match_error = ""
	if not conditions is Array:
		_match_error = "invalid_conditions"
		return false
	for condition: Variant in conditions:
		if not condition is Dictionary or not condition.get("op", null) is String:
			_match_error = "invalid_condition"
			return false
		var key: String = str(_value(condition.get("key", ""), event))
		var npc: String = str(_value(condition.get("npc", ""), event))
		var value: Variant = _value(condition.get("value", null), event)
		if condition.op in ["trust_gte","knows"] and not _touch_actor(tx,npc):
			_match_error = "unknown_actor:"+npc
			return false
		if condition.op == "inventory_gte" and not tx.inventory.has(key):
			_match_error = "unknown_item:"+key
			return false
		if condition.op in ["trust_gte","inventory_gte"] and not _integer(value):
			_match_error = "invalid_integer"
			return false
		match str(condition.op):
			"fact_eq":
				if tx.facts.get(key,null) != value: return false
			"inventory_gte":
				if not tx.inventory.has(key) or tx.inventory[key] < value: return false
			"trust_gte":
				if not tx.actors.has(npc) or tx.actors[npc].trust < value: return false
			"knows":
				if not tx.actors.has(npc) or tx.actors[npc].knowledge.get(key,null) != value: return false
			"event_eq":
				if event.get(key,null) != value: return false
			"scene_eq":
				if tx.scene != value: return false
			_:
				_match_error = "unknown_condition:"+str(condition.op)
				return false
	return true

func _effect(tx: Dictionary, event: Dictionary, effect: Dictionary, trace: Array) -> String:
	var key: String = str(_value(effect.get("key", ""),event))
	var npc: String = str(_value(effect.get("npc", ""),event))
	var value: Variant = _value(effect.get("value", null),event)
	var op: String = str(effect.op)
	var numeric: Variant = 0
	if op in ["inventory","trust","reward","timer"]:
		var field: String = "coins" if op=="reward" else ("delay" if op=="timer" else "delta")
		numeric = _value(effect.get(field,0),event)
		if not _integer(numeric): return "invalid_integer"
		if op=="timer" and numeric<0: return "invalid_delay"
	if op in ["trust","know","remember"] and not _touch_actor(tx,npc):
		return "unknown_actor:"+npc
	match op:
		"fact": tx.facts[key] = value
		"inventory":
			if not tx.inventory.has(key): return "unknown_item:"+key
			var next_inventory: int = int(tx.inventory[key]) + int(numeric)
			if not _integer(next_inventory): return "invalid_integer"
			tx.inventory[key] = next_inventory
			if tx.inventory[key] < 0: return "negative_inventory:"+key
		"trust":
			var next_trust: int = int(tx.actors[npc].trust) + int(numeric)
			if not _integer(next_trust): return "invalid_integer"
			tx.actors[npc].trust = next_trust
		"know": tx.actors[npc].knowledge[key] = value
		"remember": tx.actors[npc].memory[key] = value
		"reward":
			if not tx.rewards.has(key):
				var next_coins: int = int(tx.coins) + int(numeric)
				if not _integer(next_coins): return "invalid_integer"
				tx.rewards[key] = true
				tx.coins = next_coins
		"emit", "timer":
			var payload: Dictionary = {}
			for field: String in effect.event:
				payload[field] = _value(effect.event[field],event)
			if not _valid_event(payload): return "invalid_event"
			if op == "emit": _enqueue(tx,payload)
			else:
				var due: int = int(tx.clock) + int(numeric)
				if not _integer(due): return "invalid_integer"
				tx.timers.append({"due":due,"seq":tx.next_seq,"event":payload})
				tx.next_seq = int(tx.next_seq) + 1
		"scene": tx.scene = str(value)
		"fail": return str(effect.get("message","injected_failure"))
		_: return "unknown_effect:"+op
	trace.append("effect:%s:%s:%s" % [op,npc if not npc.is_empty() else key,str(value)])
	return ""

func restore(save: Dictionary) -> Dictionary:
	var migrated: Dictionary = save.duplicate(true)
	if not _integer(migrated.get("schema",1)): return {"ok":false,"error":"invalid_save:schema"}
	var schema: int = int(migrated.get("schema", 1))
	if schema < 1 or schema > 2: return {"ok":false,"error":"unsupported_schema"}
	if not _integer(migrated.get("content_version", 1)): return {"ok":false,"error":"invalid_save:content_version"}
	if int(migrated.get("content_version",1)) != int(_content.get("version",1)):
		return {"ok":false,"error":"unsupported_content_version"}
	if schema == 1:
		migrated.clock = migrated.get("time",migrated.get("clock",0))
		migrated.erase("time")
		var defaults: Dictionary = {"schema":2,"content_version":1,"clock":0,"scene":_initial_scene(),"facts":_content.get("initial_facts", {}).duplicate(true),"inventory":_initial_inventory(),"coins":0,"rewards":{},"actors":{},"timers":[],"queue":[],"processed":{},"next_seq":0,"trace":[]}
		for key: String in defaults:
			if not migrated.has(key): migrated[key] = defaults[key]
		if migrated.actors is Dictionary:
			for id: String in migrated.actors:
				if migrated.actors[id] is Dictionary:
					if not migrated.actors[id].has("knowledge"): migrated.actors[id].knowledge = {}
					if not migrated.actors[id].has("memory"): migrated.actors[id].memory = {}
		migrated.schema = 2
	var error: String = _validate_save(migrated)
	if not error.is_empty(): return {"ok":false,"error":error}
	var actors: Dictionary = migrated.actors
	migrated.erase("actors")
	_state = migrated
	_actors_write(actors)
	return {"ok":true,"migrated":schema == 1}

func _integer(value: Variant) -> bool:
	if value is int:
		return value >= -MAX_SAFE_INTEGER and value <= MAX_SAFE_INTEGER
	if value is float:
		return is_finite(value) and value >= -MAX_SAFE_INTEGER and value <= MAX_SAFE_INTEGER and value == int(value)
	return false

func _validate_declared_facts(facts: Dictionary) -> String:
	for key: String in _content.get("initial_facts", {}):
		if not facts.has(key): return "invalid_save:missing_fact"
		var initial: Variant = _content.initial_facts[key]
		var current: Variant = facts[key]
		if initial is int or initial is float:
			if not _integer(current): return "invalid_save:fact_type"
		elif typeof(initial) != typeof(current):
			return "invalid_save:fact_type"
	return ""

func _all_integral(value: Variant) -> bool:
	if value is int or value is float: return _integer(value)
	if value is Dictionary:
		for item: Variant in value.values():
			if not _all_integral(item): return false
	if value is Array:
		for item: Variant in value:
			if not _all_integral(item): return false
	return true

func _valid_event(value: Variant) -> bool:
	return value is Dictionary and value.get("type",null) is String and not value.type.is_empty()

func _validate_save(data: Dictionary) -> String:
	for key: String in ["facts","inventory","rewards","actors","processed"]:
		if not data.get(key,null) is Dictionary: return "invalid_save:"+key
	var facts_error: String = _validate_declared_facts(data.facts)
	if not facts_error.is_empty(): return facts_error
	for key: String in ["timers","queue","trace"]:
		if not data.get(key,null) is Array: return "invalid_save:"+key
	for key: String in ["schema","content_version","clock","coins","next_seq"]:
		if not _integer(data.get(key,null)): return "invalid_save:"+key
	if not data.get("scene",null) is String or data.clock < 0 or data.next_seq < 0: return "invalid_save:metadata"
	for key: String in _initial_inventory():
		if not _integer(data.inventory.get(key,null)) or data.inventory[key] < 0: return "invalid_save:inventory"
	for value: Variant in data.inventory.values():
		if not _integer(value) or value<0: return "invalid_save:inventory"
	for key: String in ["rewards","processed"]:
		for value: Variant in data[key].values():
			if not value is bool: return "invalid_save:"+key
	for id: String in _content.get("actors",[]):
		if not data.actors.has(id): return "invalid_save:missing_actor"
	for id: String in data.actors:
		if id.is_empty(): return "invalid_save:actor"
		var actor: Variant = data.actors[id]
		if not actor is Dictionary or not _integer(actor.get("trust",null)) or not actor.get("knowledge",null) is Dictionary or not actor.get("memory",null) is Dictionary: return "invalid_save:actor"
	for item: Variant in data.queue:
		if not _valid_event(item) or not _integer(item.get("seq",null)) or item.seq<0 or item.seq>=data.next_seq: return "invalid_save:queue"
	for timer: Variant in data.timers:
		if not timer is Dictionary or not _integer(timer.get("due",null)) or timer.due<0 or not _integer(timer.get("seq",null)) or timer.seq<0 or timer.seq>=data.next_seq or not _valid_event(timer.get("event",null)): return "invalid_save:timer"
	if data.trace.size()>128: return "invalid_save:trace"
	for line: Variant in data.trace:
		if not line is String: return "invalid_save:trace"
	if not _all_integral(data): return "invalid_save"
	return ""

func shutdown() -> void:
	pass
