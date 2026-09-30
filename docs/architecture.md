# Architecture and trust boundaries

## Three boundaries, one repository

- `addons/story_foundation/runtime`: authoritative native GDScript world state,
  condition/effect rules, events, timers, transactions, replay IDs and saves
- `addons/story_foundation/adapters`: a narrow Dialogue Manager bridge; it reads
  queries and submits commands, never lends mutable world dictionaries to prose
- `tools/authoring`: offline request/response files, validation, simulation, review,
  hash-bound approval and deterministic static build

There is no custom editor plugin in v0.1. The runtime scripts do not need a Plugins
checkbox and are not `@tool`. The example uses Dialogue Manager's own editor
plugin/importer. A custom editor is unnecessary for this workflow.

## Game-owned policy

Each game owns its world rules, characters, content IDs, presentation, art, saves
and review records. Keep that material outside the reusable addon. In the example,
`examples/village/authoring` is a sibling of `examples/village/game`, not a folder
inside its Godot export root. `scripts/prepare_example.py` assembles a disposable
project with installed addons and approved static content. It never copies the
authoring packet, raw response or approval record into that project.

Provider output cannot change gameplay policy: candidate world rules must exactly
match the packet's declared world. The v0.1 authoring schema deliberately supports
a smaller language than the native runtime. No arbitrary provider GDScript, shell,
Dialogue Manager expressions or external resource references are accepted.

## Authoritative runtime

Use `preload("res://addons/story_foundation/runtime/rule_kernel.gd").new()`.

- `configure(content, population)` initializes a new world from game policy
- `dispatch_command({id, type, ...})` is the guarded gameplay mutation boundary;
  choose stable IDs for retries. Blocked commands leave state and retry IDs unchanged
- `dispatch({id, type, ...})` is the lower-level event/timer API; unmatched events
  are accepted no-ops whose IDs are recorded. Use it only when those semantics fit
- `snapshot()` returns a deep copy suitable for local persistence
- `restore(save)` validates and migrates before atomically replacing state
- `world_fact(key, default_value)` reads world truth, returning copies
- `npc_knows(npc, key, default_value)` reads only that actor's knowledge
- `evaluate_conditions(conditions, event)` returns `{ok, matched, error}` without
  changing the world

Underscore fields are API conventions, not a GDScript security sandbox. Trusted
game code can violate conventions; review it as code. Call `configure` with
validated game policy. Its low-level contract is not an untrusted-mod loader.

Rules execute by ascending priority, then stable rule ID. Events drain FIFO within
one transaction. Actor records are staged on first touch. Invalid effects, failed
conditions with errors and the 64-event cycle ceiling roll the whole transaction
back, including clocks, timers and actors. Completed command IDs and reward IDs
are persisted. A repeated command ID is a successful no-op; this is retry safety,
not permission to reuse one ID for different intended commands.

## Actual Dialogue Manager integration

The official pinned Dialogue Manager addon parses the generated
`presentation.dialogue` resource. The example asks its autoload for lines and
responses with the bridge passed in `extra_game_states`. The generated DSL contains
only fixed calls to `story.branch_available` and `story.choose` plus validated
literal text and stable IDs. It never assigns a world dictionary field.

`branch_available` returns only the first matching branch, otherwise fallback.
`choose` checks that the displayed branch is still selected, then submits that
command to `dispatch_command`, whose kernel checks the rule guards
inside the transaction after any pending events. An unavailable command aborts
the whole transaction without consuming its ID. A stale selection is rejected. The
bridge gives retries of the same choice within one dialogue session the same
command ID; beginning a new conversation creates a new session.

The demo UI disables concurrent line requests; display choices never mutate state
by themselves. The runtime is synchronous and single-threaded. This is a narrative
foundation, not a general ECS, multiplayer authority server or visual story editor.

## Claims and knowledge

World truth and NPC knowledge are independent. A true world fact cannot satisfy a
`knows` condition. The offline checker requires declared NPC factual claims to have
both matching truth and speaker-knowledge guards in that branch. Simulation checks
required branches with specified command sequences and expected states.

This checks annotations, not natural-language entailment. Omitted claims, subtext,
contradictions, tone and psychological realism still need human review. No model
reviewer or factual omniscience detector is claimed. The shipped public prose is a
synthetic fixture; no paid or live LLM call has been tested.

The bridge includes `release_dialogue_resource(resource)` for the pinned Dialogue
Manager version's transient visited-line back-references. Call it only after
pending line requests finish and when no other view uses the resource; the demo
releases its resource on exit. Upstream addon files are not patched.
