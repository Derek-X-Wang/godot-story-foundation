# Architecture and trust boundaries

## Design decisions

The goal is repeatable production across games with distinct mechanics and
creative identities. Foundation supplies reusable low-level primitives, tools
and contracts; it is not a mandatory universal game framework. The village is a
neutral integration fixture, not the product's narrative or design target.

### Optional composition, explicit contracts

Modules and pipelines must be independently optional, composable and extensible.
A game should be able to select a music pipeline without installing art,
dialogue or world-state systems. That is an acceptance target for a future music
module, not a capability shipped by v0.1. The narrative toolkit and experimental character-sprite pipeline are narrow
subsets of this direction, alongside independently optional scene navigation/depth
primitives. Portraits, scene-art, UI/icons, VFX and music remain
separate future subpipelines; see [art contracts and status](art.md).

Each module must state its inputs, outputs, versions, errors, dependencies,
state ownership and any required lifecycle steps. Keep that contract small and
explicit. Shared identifiers or formats may be deliberate contracts; an
unrelated pipeline, global singleton or incidental file layout must not become
a hidden prerequisite. A module may have real dependencies, but they must be
declared and confined to its function.

Replace pipeline stages, generation providers, file formats and runtime
integrations through adapters at those boundaries. Do not assume interchangeable
implementations have identical semantics: validate the replacement's contract
and document conversions, costs and guarantees. The current authoring workflow
exports/imports provider-neutral files; it has not exercised a live provider.

### Defaults, templates and game-specific code

The included workflow and game template are optional conveniences. Games may
bypass them, compose only useful primitives, or implement unique mechanics in
game-owned code. Prefer composition/adapters over a separate Foundation fork for
each game. If a reusable extension point is missing, design and test a small
upstream contract rather than hard-coding one game's policy into the core.

For example, a game-specific rhythm mechanic can own its timing model and use
only an asset pipeline; it need not represent rhythm timing as dialogue rules.
A second story using only changed data is a useful test of one template's reuse,
not a universal requirement that every new game be data-only or code-free.

### Definitions, state and selected guarantees

Keep immutable definitions (rules, content and asset descriptions) separate from
mutable runtime state (progress, inventory and mechanic-specific state).
Definitions identify the behavior/version being executed; state records one
playthrough. The native kernel copies configured definitions and exposes copied
queries/snapshots rather than lending mutable records to presentation code.

Optional composition does not weaken the guarantees of a selected module:

- When using the reviewed authoring workflow, approval binds the exact input,
  candidate and review versions/hashes. Editing text invalidates that approval
  and requires a new review/build; generated output must not retain a stale
  "approved" label. See [offline authoring](authoring.md)
- When using saves, explicitly define which state is covered. Custom mechanics
  own their serializers, schema versions and migrations, with restore/replay
  tests. Foundation's current snapshot only covers the native kernel's state;
  there is no automatic custom-state serializer/plugin hook or automatic
  transaction spanning game systems. See [versions and saves](versioning.md)
- A custom adapter/workflow must document which validation, review, transaction
  or save guarantees it preserves and test those claims. Bypassing a workflow
  does not imply that its guarantees still apply

### Backend choice and tradeoffs

Native GDScript is the implemented default. A future Bevy backend would require
an explicit interface, adapters and equivalence tests for the promised behavior
(including ordering, transactions, queries and save compatibility where used).
This document does not establish that interface or promise an automatic,
zero-cost backend switch.

Alternatives and consequences:

- A mandatory all-in-one framework simplifies one standard path but couples
  unrelated features and constrains unusual games. Optional modules instead
  require explicit integration, dependency and compatibility testing
- One universal data schema makes a second templated story easy but cannot
  express every mechanic well. Game-owned code preserves creative freedom at
  the cost of its own validation, tests and serialization
- Per-game core forks unblock local changes quickly but multiply maintenance.
  Small shared extension contracts and game-owned adapters keep the core reusable,
  while still requiring deliberate work for genuinely new behavior
- The native backend minimizes today's integration surface. Backend abstraction
  is justified by a concrete implementation and validated contract, not an
  untested promise of portability

### Acceptance examples

For a new or changed module, demonstrate the relevant boundary rather than
requiring every game to use the same stack:

1. Standalone use: exercise it with only declared dependencies. Today, the native
   runtime can be used without Dialogue Manager or offline generation; a future
   music pipeline must also work without narrative/world-state or art modules
2. Substitution: replace a stage/provider/format through an adapter, check its
   contract, and show unrelated modules still work without coordinated edits
3. Unique mechanics: integrate game-owned behavior without editing/forking core,
   with explicit ownership and tests for any selected save/review guarantees

These are design acceptance criteria, not claims that every possible substitution
or custom mechanic is supported and tested in v0.1. The implemented boundaries
below and [verification record](testing.md) describe the current narrower scope.

## Implemented boundaries (v0.1)

- `addons/story_foundation/runtime`: authoritative native GDScript world state,
  condition/effect rules, events, timers, transactions, replay IDs and saves
- `addons/story_foundation/scene`: independently usable rectangle navigation and
  deterministic depth sorting; no runtime, art, addon or autoload dependencies.
  Explicit geometry configuration and game-owned adapters; see [scene contracts](scene.md)
- `addons/story_foundation/adapters`: a narrow Dialogue Manager bridge; it reads
  queries and submits commands, never lends mutable world dictionaries to prose
- `tools/authoring`: offline request/response files, validation, simulation, review,
  hash-bound approval and deterministic static build
- `tools/art`: optional offline character-sprite manifests, provenance and pixel
  validation, deterministic atlases, optional Aseprite source and Godot consumer
  adapters. No narrative runtime dependency. Contract v1 is experimental; two
  private native character sources have exercised static and moving export/consumer
  reuse. Pose authoring, gait approval and game integration are separate. See [art boundaries](art.md)

There is no custom editor plugin in v0.1. The runtime scripts do not need a Plugins
checkbox and are not `@tool`. The example uses Dialogue Manager's own editor
plugin/importer. A custom editor is unnecessary for this workflow.

## Optional test-only execution and replay

`tools/regression` runs trusted local argv commands with a versioned strict result
protocol, timeouts, exact counted diagnostic allowances, explicit missing lanes and
coverage targets. It has only a Python standard-library dependency.
`addons/story_foundation/testing/replay_record.gd` is independently optional and
uses Godot built-ins only. It validates and compares semantic records; it never
applies a gameplay action or restores a save by itself.

Game adapters own scenario IDs, action/guard/ending catalogs, snapshots, initial
state setup, real UI/runtime execution, expected results and invariants. Neither
module depends on the narrative kernel, Dialogue Manager, scenes or art. The
public examples are original neutral synthetic fixtures. Private story IDs and
fixtures belong in the consuming game. See [runner protocol](../tools/regression/README.md)
and [replay contract](replay.md). State exploration, shrinking and browser drivers
remain unimplemented; native packed checks do not establish Web runtime coverage.

## Game-owned policy

Foundation owns reusable contracts, validators, tooling and neutral examples.
Each game owns its mechanics, world rules, characters, content IDs, presentation,
story, art/music assets, project-specific prompts, saves and review records. Keep
that material outside the reusable addon. In the example,
`examples/village/authoring` is a sibling of `examples/village/game`, not a folder
inside its Godot export root. `scripts/prepare_example.py` assembles a disposable
project with installed addons and approved static content. It never copies the
authoring packet, raw response or approval record into that project.

The public repository must exclude private story/prompt/review material, keys or
other secrets, proprietary or license-restricted assets, and large game asset
payloads. Keep those in the game's appropriate private storage; public examples
must be intentionally redistributable, neutral fixtures with correct licenses.

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
