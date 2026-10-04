# Optional bounded narrative contracts (report schema 1)

`addons/story_foundation/testing/narrative_contract.gd` is a small **test-only**
exact-state breadth-first explorer. Its sole dependency is the sibling
[`replay_record.gd`](replay.md), whose strict canonical JSON implementation it
reuses. It has no runtime kernel, Dialogue Manager, scene, art, autoload, quest DSL
or framework dependency. Select it independently; no runtime installation is
required. The consuming game owns creative intent, requirements, definitions,
mutable state, snapshots, saves, admission, time costs, update ordering and UI.
The helper supplies bounded traversal and reports, not a narrative-quality oracle.
Catalog parity cannot show that a missing choice should have existed.

## Run the neutral examples

With Python 3.11+ and Godot 4.6.3, from the repository root:

```sh
python3 scripts/test_narrative_contracts.py --godot /path/to/godot
```

This creates a fresh project with only the two helpers and an original neutral
control-panel fixture. It runs unit tests and explores the fixture, deletes the
first project and repeats in a fresh relocated project without import caches.
Only afterward does it add the native kernel and actor-record dependency for a
separate command/projection sample. No downloaded addon or game assets are needed.
The existing [`tools/regression`](../tools/regression/README.md) runner checks
real process exits, complete diagnostics and strict result envelopes. There is
no duplicated subprocess protocol.

Named reports and complete logs are retained under `.build/narrative-contracts/`;
use `--output PATH` for another directory. The four deliberate mutations produce
**failed** reports. The outer verification accepts them only with exit 1, no
engine diagnostics, successfully executed callbacks and the specific independent
semantic violation. Crashes, syntax errors and malformed reports are not mutation
successes. Normal example and unit reports must pass. These are source-lane
checks; native packs, browsers and other platform gameplay remain unclaimed.

For manual use, copy both helpers and their `.uid` files into an empty Godot
project alongside [`neutral_adapter.gd`](../examples/narrative_contracts/neutral_adapter.gd)
and [`run.gd`](../examples/narrative_contracts/run.gd), then run:

```sh
godot --headless --path /path/to/project --script res://run.gd
godot --headless --path /path/to/project --script res://run.gd -- --mutation missing_option
```

The first exits 0; the meaningful mutation exits 1. For `--kernel`, also copy
`kernel_adapter.gd` and native `rule_kernel.gd`/`actor_record.gd` at their declared
addon paths. The script is a runnable test sample, not a complete playable game.

## Small callback contract

Call `Explorer.explore(spec, reset, snapshot, restore, step, observe)`.
`spec` has exactly these fields:

- `name`: nonempty String identifying this authored contract
- `actions`: nonempty unique String array of declared route/action **macros**
- `required_goals`: nonempty unique String array of intended goals
- `max_depth`: nonnegative integer maximum macro-action count
- `max_states`: positive integer ceiling on retained exact snapshots

The synchronous, trusted, game-owned callbacks are:

- `reset() -> {ok: bool}` creates the declared initial state through real setup
- `snapshot() -> Dictionary` copies **all** state affecting future results or
  observations: receipts, timer/queue order, history, RNG, custom mechanics and
  selected presentation state. Completeness is the author's responsibility
- `restore(snapshot) -> {ok: bool}` restores a previously reached snapshot;
  immediate recapture must match exactly or exploration fails closed
- `step(action_id) -> {ok: bool, accepted: bool}` executes a real macro through
  the same boundary as play. Ordinary unavailability returns
  `ok: true, accepted: false`; execution errors return `ok: false`. An accepted
  retry receipt is not automatically a new transition: preserve and test the
  game's operation-ID semantics
- `observe(snapshot) -> {goals: Array[String], violations: Array[String]}` is an
  independently authored, read-only oracle. Observed goals must be declared.
  Derive required choices from intent/prerequisites and compare against actually
  offered choices, rather than copying the implementation's command catalog

All arrays above contain unique nonempty Strings. Snapshots use the replay
helper's strict canonical JSON domain. No history, receipts, timestamps or other
fields are silently removed. The kernel sample explicitly normalizes its known
JSON save domain to String-keyed JSON. The generic helper never stringifies
arbitrary Godot objects. Complete canonical JSON bytes key states, rather than a
lossy fact abstraction or hash alone.

The helper checks observations at every retained reached state and after rejected
attempts; rejection must preserve the entire selected snapshot. If a game
intentionally renders rejection feedback, define explicitly which transient
presentation belongs in its atomic snapshot, or represent the completed macro
appropriately in its adapter. Never omit authoritative or future-relevant state
merely to obtain a pass. Callbacks get deep-copied inputs but are trusted code;
they must not mutate unrelated state, throw engine errors or cause external
side effects. The outer runner also checks errors, timeouts and missing results.

Use a disposable isolated instance, never the live player's state. The instance
is left at the last explored state; release its nodes/resources afterward. There
is no sandbox, automatic custom-state serializer or production save migration.

## Reports and honest bounds

`ok` means the callback protocol executed, not that requirements passed. `passed`
is true only for `status: bounded_pass`. Other statuses are:

- `contract_failed`: witnessed invariant/option violation, or a required goal
  absent after completing the declared depth-limited exploration
- `inconclusive`: the state ceiling interrupted traversal without an already
  witnessed violation. Previously reached goals cannot turn incomplete invariant
  checking into a pass
- `execution_error`: invalid contract, snapshot, callback, restore or transition;
  includes the offending macro trace and never claims a completed search

Successful protocol reports include declared actions/goals, bounds,
retained/expanded states, accepted/rejected edges, observation count, depth
frontier, state-ceiling flag, shortest goal traces, missing goals within the bound
and shortest counterexamples per requirement. Output is deterministic for a
deterministic adapter and contains no elapsed-time noise.

FIFO traversal gives shortest traces by **macro count within this declared
subgraph**, not seconds, clicks or travel. Fixed action order breaks ties.
Depth-frontier states are checked but their outgoing actions are not. State-cap
interruption stops new edges, then checks all already-retained queued snapshots
before finalizing shortest counterexamples; it remains incomplete. Exact
histories and retry IDs can make state spaces unbounded despite finite visible
facts; bounds are part of the tested requirement. Missing goals are **not** global
impossibility proofs. Shortest BFS traces are not a general failure shrinker.
Coverage excludes omitted actions, seeds/state, asynchronous UI scheduling,
other platforms and unbounded play. Restore fidelity proves only equality of the
selected snapshot, not its completeness or production save behavior.

## Entry-state information order

A downstream fixture whose `reset` has already granted introductory knowledge
cannot certify how that knowledge was acquired. State the entry point explicitly.
For an opening-order requirement, start through the game's actual fresh-start
setup before the first relevant interaction, with no progress or knowledge seeded
past that boundary. Keep the downstream contract for its own scope.

Author both sides of the information boundary independently of implementation:

- Which options must be absent before the player receives the prerequisite, and
  which must be offered afterward? Distinguish world truth, actor knowledge and
  information presented to the player; one does not establish the others
- What readable event and acknowledgment, if required by the design, commit that
  knowledge? Split macros at those observable boundaries so a single action does
  not hide premature choices or side effects between opening and acknowledgment
- Which ordinary alternatives must remain available without optional discovery?
  For example, if a neutral terminal requires acknowledging an access notice
  before offering a restricted route, optional inspection of a diagnostic panel
  must not become a hidden prerequisite for the independently allowed help route
- Can cancellation, reentry or a loaded save skip the prerequisite or lose an
  already earned option? Check the game's declared persistence policy through
  its real setup/save path, rather than assuming explorer restore covers it

Assert forbidden-before and required-after choices at each relevant state, and
retain a witness for intended routes with optional investigation omitted. Merely
reaching an ending or enumerating existing commands cannot establish these
requirements. Include presentation/progress state when it affects the oracle or
future actions. A synchronous macro graph does not cover real UI callback timing;
pair it with the [interrupted-UI recipe](testing.md#consumer-interrupted-ui-contracts).

## Actual update and projection boundary

[`kernel_adapter.gd`](../examples/narrative_contracts/kernel_adapter.gd) uses the
native kernel, an attached Label and one consumer-owned step function: guarded
command/effects, time advance and due timers, then Label refresh. Publishing
after defer at the cutoff succeeds because committed effects precede timer
closure. Full kernel state, history and actual Label text enter exact-state keys.
Failed command results return before success text is assigned. The kernel itself
does not make the command and cost dispatches jointly atomic; a failure between
them is an adapter execution error, not a rejected unchanged command.

The sample directly verifies that unavailable initial publication preserves the
entire authoritative kernel snapshot. The `false_success` mutation still preserves
that snapshot but renders `Published`; the independent oracle rejects it with
`rejection_must_not_render_success`, shortest trace `[publish]`. The
`stale_projection` mutation commits correctly yet fails
`committed_state_reaches_label`. State-transaction tests alone miss both mistakes.

These are headless checks against an actual attached Label, not pixels, browser,
animation or Dialogue Manager traversal. Consumers own their GUI refresh and
must test their selected real view and execution path. Human prose review remains
necessary.

## Author-reviewed RED → GREEN → meaningful mutation

1. Before repair, independently write intended choices, invariants, distinct
   outcomes and timing/deferral commitments in the consuming game's contract.
   Review them against author intent, not implementation catalogs. Record exact
   source/content/build identity and scope. Reuse existing replay identity
   records for durable replay traces; this helper adds no second replay format
2. Run the real broken path and retain RED evidence naming a semantic requirement
   and minimal macro counterexample. Keep missing implementation options in the
   authored actions and goals
3. Repair game-owned policy, ordering or projection. Re-run unchanged requirements
   to GREEN, including meaningful outcome combinations, rejection, defer and
   applicable save/UI paths. Review requirement changes rather than deleting
   assertions to silence failures
4. Introduce valid-interface mutations recreating the defect. This sample removes
   a required right-panel option, locks confirmation after defer, skips a committed
   Label refresh and renders success after rejection. Each must fail its named
   semantic requirement. Restore the fixed build and rerun
5. Have an author review requirements and the actual prose/experience. Mechanical
   reachability does not approve tone, implication, hidden options or narrative
   quality. Keep game IDs, characters, assets, saves, review packets and reports
   in the consuming repository

The neutral runner exercises a reversible missing-option RED, fixed GREEN and
four meaningful mutation controls. It does not claim a historical production bug
or import private narrative contracts. No runtime dependency, quest DSL, ECS or
backend migration is introduced.
