# Versions, upgrades, replay and saves

Pin the independently meaningful boundaries that the game selects:

| Boundary | v0.1 value | Meaning |
| --- | --- | --- |
| Foundation release/API | 0.1.0 | Code API and package |
| Save schema | 2 | Snapshot structure; schema 1 migration supported |
| Authoring content schema | 1 | Packet/candidate/build representation |
| Optional scene primitive API | 1 | Geometry/ordering contract; no save ownership |
| Optional audio primitive API | 1 | Bus creation/preferences/gain sampling; caller owns defaults and migrations |
| Game content version | Positive integer in content | Rules, stable IDs and save compatibility |

The dependency lock separately pins Godot 4.6.3 and the exact Dialogue Manager
commit and archive hash. Python 3.11+ is supported, with standard-library-only
authoring tools. A lock is not a promise that later upstream versions work.

## Use in multiple games

Build the release addon ZIP, record its SHA-256 and release tag/commit in each
consuming game's dependency manifest, and commit the installed addon directories.
The ZIP contains `addons/story_foundation` and the pinned
`addons/dialogue_manager`, including upstream license notices. Unzip at the game
project root. Keep game rules, UI and content outside both addon directories.

Install the runtime alone if Dialogue Manager is unnecessary. Do not fork runtime
code into each game's business logic. A Git submodule pinned to an exact commit is
an optional workflow; remember that a submodule checks out the whole repository,
not just the addon subtree. Release ZIP installation is the simple default.

Scene-only consumers may select either independent script and its UID instead of
the full addon bundle. The [scene-only package](scene.md#packaging-pins-and-upgrades)
includes deterministic file hashes and no Dialogue Manager or narrative runtime.
Pin its exact source commit and selected hashes in the consuming game.

Audio-only consumers may select any of the three independent scripts without UID
sidecars or the full addon bundle. The [audio-only package](audio.md#packaging-pins-and-verification)
includes deterministic hashes. Its bus-name ConfigFile sections retain missing
caller defaults; renamed buses and changed preference semantics require explicit
game-owned migration. Pin the source commit and selected file/archive hashes.

## Save ownership and reconstruction

A save should record the authoritative facts needed to continue the game under
its declared policy. Rebuild derived presentation from those facts where possible:
labels, available-choice lists, cached routes and animation projections should not
silently become competing sources of truth. This distinction is about ownership,
not a requirement to adopt ECS or serialize every engine object.

Define the continuation boundary explicitly. A checkpoint-only game may reopen a
conversation from a safe authored entry. A game promising mid-interaction resume
must own and serialize the additional semantic state it needs, such as a stable
conversation/step ID, acknowledgment status and pending commitment. Preserve
timers, RNG state or custom mechanic progress when they affect future outcomes;
do not discard them merely because they are outside the narrative kernel.
Callbacks, live node references and animation handles are not durable substitutes
for that contract. On restore, invalidate old callbacks and reconstruct the view
from restored state before accepting new input.

Foundation's snapshot covers only its kernel state. It does not save a consumer's
dialogue position, UI lifecycle or custom mechanics, nor does it make restoration
across multiple game-owned systems atomic. Declare those owners, versions and
restore order in the consumer; validate compatibility before replacing live state.

For each supported continuation boundary, compare an uninterrupted run with a
save/fresh-load/continue run using the same subsequent actions. Assert semantic
outcomes and the actual presented options/text, plus no duplicate rewards,
commits or time charges. Include interruption before and after the commit point,
and explicitly test rejected or migrated old saves. Pair these checks with the
[interrupted UI recipe](testing.md#consumer-interrupted-ui-contracts) and
[semantic replay scope](replay.md); replay alone is not save/restore evidence.

## Upgrade procedure

1. Commit a clean baseline and preserve representative save fixtures
2. Record old and new Foundation, Godot, Dialogue Manager and tool versions
3. Replace the addon directories as a unit; do not merge arbitrary files from two
   versions
4. Run offline validation and branch simulations; a tool/schema change can require
   renewed human review and a fresh deterministic build
5. Replay golden command sequences and compare semantic state, then test loading
   actual old saves. Exercise failure rollback, timers and duplicate submissions
6. Import/run the project and its UI integration tests before shipping
7. Keep the old package and saves until compatibility is established

The kernel migrates schema 1's `time` field to schema 2's `clock` and fills supported
legacy fields. Unknown future schemas, malformed saves and different game content
versions are rejected without mutating live state. Declared initial facts retain their
types, and all numeric state must stay within the exact JSON integer range
±(2^53−1). There is no arbitrary automatic
content migration. A game must explicitly migrate renamed IDs or changed policies,
bump its content version and test the migration before accepting older saves.

Stable content IDs are part of compatibility: avoid deriving them from prose or
line positions. A wording-only edit still requires fresh approval; decide whether
it changes game content/save semantics separately. Do not alter rule order, event
meaning or rewards under a supposedly identical content version without replay
review.

The runtime stores an idempotency ledger and bounded trace, not a durable command
journal. A game that needs complete replay must persist the original commands and
content/tool versions itself. Save size grows with distinct processed IDs. There
is no unbounded-session compaction policy or cross-machine synchronization in v0.1.
