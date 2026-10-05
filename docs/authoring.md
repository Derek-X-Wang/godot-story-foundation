# Offline authoring workflow

The v0.1 CLI is Python 3.10+ and standard-library only. It never calls a model, reads credentials, makes network requests, or sends story data to a provider. You may use the checked-in original village response entirely offline. A provider integration, if you choose to build one, is an explicit export/import boundary.

## Quick start: the synthetic demo

Run from the repository root:

```sh
python3 -m tools.authoring build \
  --packet examples/village/authoring/packet.json \
  --candidate examples/village/authoring/candidate.json \
  --review examples/village/authoring/review.json \
  --approval examples/village/authoring/approval.fixture.json \
  --output /tmp/story-foundation-build \
  --allow-test-fixture
```

This exercises the real validator, simulator, exact-byte approval checks, and compiler. The approval is prominently labeled **synthetic test fixture**, not a human review. The same build fails if you omit `--allow-test-fixture`. Do not use that switch to bypass review of your own content.

Build outputs:

- `content.json`: approved static world policy and dialogue data
- `presentation.dialogue`: generated Dialogue Manager source using only fixed bridge calls
- `build-manifest.json`: runtime file hashes, content identity/version, tool version, and the synthetic-fixture flag
- `audit.json`: declared model, prompt/tool version, input/output hashes, reviewer, and review status; keep outside the game

Only the first three belong in a shipped game. The CLI refuses to write any authoring/build output inside an existing Godot project root. Build into a separate directory, then stage the three compiled runtime files. Do not copy packets, requests, raw responses, candidates, reviews, approvals, or the audit record into the project.

## A real review cycle

Start by writing a packet following `schemas/packet.schema.json`, using the village packet as an example. The packet is human-owned and defines the scene, allowed facts and commands, gameplay rules, and branch simulations.

```sh
# 1. Export a provider-neutral request. This does NOT execute a provider.
python3 -m tools.authoring export-request \
  --packet my-scene/packet.json --output my-scene/request.json

# 2. Supply a hand-written or separately obtained raw response object.
# The checked-in offline response is a useful first exercise.
python3 -m tools.authoring import-response \
  --packet my-scene/packet.json --response my-scene/response.json \
  --model-declared hand-written-local --output my-scene/candidate.json

# 3. Validate and inspect branch simulations independently if desired.
python3 -m tools.authoring validate \
  --packet my-scene/packet.json --candidate my-scene/candidate.json
python3 -m tools.authoring simulate \
  --packet my-scene/packet.json --candidate my-scene/candidate.json

# 4. Produce review.json and the readable review.txt beside it.
python3 -m tools.authoring review \
  --packet my-scene/packet.json --candidate my-scene/candidate.json \
  --output my-scene/review.json
# Optional: --baseline previous-build/content.json gives a textual change diff.

# 5. A PERSON reads the packet, candidate, diff, claims, and simulations.
# Run this only after that review; supplying a reviewer alone is insufficient.
python3 -m tools.authoring approve \
  --packet my-scene/packet.json --candidate my-scene/candidate.json \
  --review my-scene/review.json --reviewer "Your name" --yes-i-reviewed \
  --output my-scene/approval.json

# 6. Compile the exact reviewed bytes.
python3 -m tools.authoring build \
  --packet my-scene/packet.json --candidate my-scene/candidate.json \
  --review my-scene/review.json --approval my-scene/approval.json \
  --output /tmp/my-scene-build
```

Import, validate, simulate, and review never create an approval. No production command manufactures a synthetic approval. The checked-in test artifact is deliberately separate. Unit tests exercise the affirmative human-approval code path with explicitly test-only identities; they are not reviews of production content.

Packet, candidate, and review hashes bind **exact file bytes**, including whitespace. Changing any of those invalidates the existing chain. Re-import after changing a packet; re-run review and obtain a fresh explicit approval after changing a candidate. The candidate also contains a canonical content hash. Rewriting an approval is not a substitute for re-review.

The approval record is a local review gate, not a cryptographic identity or a tamper-proof signature. Anyone with write access to all files could forge one. Use repository permissions, code review, signed commits, or a separately authenticated signing service where adversarial audit guarantees are required. `model_declared` is caller-supplied provenance, not a verified claim about which model actually ran.

## Packet and content contract

`schemas/packet.schema.json` and `schemas/content.schema.json` are closed Draft 2020-12 JSON Schemas. The bundled validator implements the exact schema subset used by these files without fetching remote schemas. Semantic checks add IDs, references, types, knowledge guards, policy preservation, and fixture coverage.

A packet contains:

- `packet_id`, `prompt_version`, `content_id`, and `content_version`
- A `scene_card` with purpose, location, and the complete expected dialogue/branch ID sets
- `personas` for speaking actors, including voice and knowledge policy
- Only `relevant_world_context` needed for this scene
- Explicit registries for actors, facts, items, scenes, memory keys, rewards, and commands
- The complete authoritative `world` policy for this small content unit
- Deterministic simulation `fixtures`

An imported response must contain exactly:

```json
{
  "schema_version": 1,
  "content_id": "example_scene",
  "content_version": 1,
  "world": {
    "version": 1,
    "actors": ["player", "keeper"],
    "initial_facts": {"bridge_closed": true},
    "initial_inventory": {"chalk": 1},
    "initial_scene": "village",
    "rules": []
  },
  "dialogues": []
}
```

This abbreviated shape is illustrative; valid content must include registered rules and populated dialogues. `world` must match the packet exactly, including array order and value types. A provider cannot add rewards, invent commands, alter inventory, or change gameplay policy. Policy edits happen in the human-owned packet and require the complete review cycle again.

Each dialogue contains `id`, `speaker`, a nonempty ordered `branches` list, and a mandatory `fallback`. Each regular branch has `id`, a nonempty `when` list, single-line `text`, `claims`, and `choices`. The fallback has the same fields except `when`, and must have no claims. Choices contain only `id`, `text`, and a registered `command`. Every command has exactly one authoritative rule. Branches use first-match order; the fallback is selected only when no branch matches.

All identifiers use `[a-z][a-z0-9_]{0,63}`. Duplicate IDs, unknown fields, unknown references, Boolean numeric deltas, and fact values with mismatched types are rejected. Facts support Boolean, integer, and string values. Every integer anywhere in the input must be within ±(2⁵³−1), the exact common JSON/Godot range; narrower field limits also apply. Simulator arithmetic rejects overflow transactionally. No floats, null facts, dynamic variable references, arbitrary predicates, embedded code, or event interpolation are accepted.

### Restricted rule vocabulary

Every `when` condition is ANDed. The supported forms are:

```json
{"op":"fact_eq", "key":"bridge_closed", "value":true}
{"op":"knows", "npc":"keeper", "key":"bridge_closed", "value":true}
{"op":"trust_gte", "npc":"keeper", "value":1}
{"op":"inventory_gte", "key":"chalk", "value":1}
{"op":"scene_eq", "value":"village"}
```

Supported effects are:

```json
{"op":"fact", "key":"bridge_closed", "value":true}
{"op":"know", "npc":"keeper", "key":"bridge_closed", "value":true}
{"op":"trust", "npc":"keeper", "delta":1}
{"op":"remember", "npc":"keeper", "key":"heard_news", "value":true}
{"op":"inventory", "key":"chalk", "delta":-1}
{"op":"reward", "key":"safe_path_reward", "coins":5}
{"op":"scene", "value":"village"}
```

A debit needs a matching inventory guard for the total consumed quantity. Rewards are keyed one-time grants. Memory is a separate actor-local store; knowing a fact is different from the fact being globally true. The broader runtime may support other operations, but v0.1 authoring intentionally rejects them, including `emit`, `timer`, `event_eq`, `fail`, and all expression evaluation.

### Honest NPC knowledge

An asserted fact is annotated as `{"fact":"bridge_closed","value":true}` in `claims`. For each annotation, the same branch must contain both:

- `fact_eq` for the identical fact/value, establishing current world truth
- `knows` for the dialogue's speaker and the identical fact/value, establishing personal knowledge

The player's knowledge does not stand in for the NPC's. A fallback cannot contain factual claim annotations. The validator checks these declarations; it cannot infer every assertion from natural-language prose. A human must ensure claims are complete, uncertainty is honest, and lines do not imply forbidden knowledge. Do not treat machine validation as a prose truth detector or a full narrative-quality check.

### Consumer review when adding content

For a new actor, scene or interactable, a short game-owned note can connect intent
to observable behavior: what the actor wants, what they know and how they learned
it, where they can be encountered, what an interaction changes, and what the UI
may truthfully report. Mark unsettled story details as proposed or unknown rather
than silently turning them into facts. This is an optional design-review aid,
not a new schema or a guarantee that motives and causal relationships make sense.

Keep distinct transitions distinct in the game's chosen state model. For example,
an item offered, handed to a carrier, received at its destination, and reported
back to the player need not occur together. Custody does not establish receipt;
world truth does not establish an actor's knowledge. Check dialogue, visible
actors/targets, journal and ending text against the same authoritative state.

Add only the scenarios relevant to that addition: first visit after progress
elsewhere, revisit after an actor moves or a route closes, or an item whose
custody changes before confirmation arrives. Assert the selected branch and
actual displayed text, not just that the content parses. An earlier briefing may
remain historical, but must not be worded as an unchanged present condition.

Record which additions used existing data contracts and which needed game-owned
code. New movement, multi-item custody, scheduling or presentation can require
custom adapters and save validation; do not label the whole expansion data-only.
See [state ownership](architecture.md#definitions-state-and-selected-guarantees)
and the [consumer build recipe](testing.md#consumer-content-build-and-capture-recipe).

For an optional general review and route-isolated read, use the
[narrative-review worksheet](narrative-review.md). Keep author-only intent separate
from player-visible observations; this aid does not create an approval record.

### Branch simulations

Every fixture starts from the initial world with empty actor knowledge/memory, zero trust, and zero coins. Its steps dispatch named commands with stable `action_id` values and expected statuses (`applied`, `blocked`, or `duplicate`). Failed guards must leave state unchanged and do not consume the action ID. Accepted duplicate IDs have exactly-once semantics. The final assertions check selected dialogue branches and optional world facts, inventory, coins, and scene.

Every declared branch, including each fallback, must appear as a fixture's expected final selected branch. Missing coverage, wrong state, wrong dispatch status, and unexpected selected branches fail import, review, approval, and build. This is explicit scenario coverage, not exhaustive state-space verification.

The village's four fixtures cover:

1. Honest ignorance before observing the bridge
2. Player-only discovery that leaves Mira uninformed
3. Sharing knowledge, rejecting premature sharing, and duplicate action IDs
4. Guarded path marking, inventory conservation, one-time reward, and repeat rejection

## Dialogue Manager and runtime boundary

Generated source contains only fixed `story.branch_available(dialogue_id, branch_id)` guards and `story.choose(dialogue_id, branch_id, choice_id)` calls. IDs are strictly validated. Provider prose is inserted only as plain dialogue/choice text; control characters, multiline text, and reserved markup characters (`[ ] { } \\ < > # |`) are rejected. Choice text also rejects colons, which Dialogue Manager can interpret as a character prefix; speaker IDs starting with `else` or `elif` are reserved because its parser recognizes those prefixes as control flow. The compiler never emits provider-authored expressions or commands.

The runtime bridge owns the `story` binding. It must select the authoritative first matching branch, revalidate the current branch and command guards when choosing, assign/reuse stable session action IDs, and dispatch the named registered command transactionally. Displaying a choice is not permission to skip a guard. A stale or premature choice can be rejected without mutating state. The bridge's runtime tests complement the Python reference simulations; neither implementation silently treats generated text as gameplay authority.

## Provider hook protocol

No SDK is bundled. A separately authorized provider adapter can:

1. Read `request.json`, including its exact `packet_hash`, instructions, packet, and response schema
2. Send only the intended scene packet to the chosen provider using credentials managed outside this repository
3. Write the provider's **raw JSON object** to a response file, without code fences or additional metadata
4. Pass that file to `import-response` with the actual declared model name/version

The importer is provider-agnostic and treats all returned content as untrusted. It rejects malformed UTF-8 JSON, duplicate keys, non-finite numbers, inputs larger than 2 MiB, unknown operations/fields, policy mutations, unsafe text, and failed simulations. It makes no network call and never inspects environment credentials. Do not include hidden reasoning or chain-of-thought in responses or audit metadata.

Keep source packets and audit/reviewer history outside the runtime/export root. Review provider privacy, retention, cost, and data-sharing terms yourself before sending non-public story material. The offline fixture sends nothing anywhere.

## Reproducibility and tests

Outputs use sorted UTF-8 JSON and deterministic source generation. Builds contain no timestamps, absolute source paths, machine usernames, random identifiers, or model reasoning. Rebuilding the same approved inputs produces byte-identical runtime files, manifest, and audit. Manifest SHA-256 values cover the actual emitted runtime bytes.

```sh
python3 -m unittest discover -s tests/python -p 'test_authoring*.py' -v
```

The tests cover approval gates and mutation invalidation, honest ignorance/discovery, typed registries, unknown operations, missing branches/fallback, knowledge annotations, branch coverage, stale choices, idempotency, injected DSL text, offline import/export, and deterministic build hashes. Error exits use status 2 and do not write build files before validation succeeds.
