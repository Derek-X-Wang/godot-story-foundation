# Godot Story Foundation

A small **Godot 4.6.3 / GDScript narrative foundation**: authoritative world state,
NPC knowledge, guarded choices, atomic rule transactions and local saves, plus an
optional offline dialogue authoring and review workflow.

**Status: v0.1.0.** Native GDScript only. The example uses the actual official
[Dialogue Manager 3.10.4](https://github.com/nathanhoad/godot_dialogue_manager/releases/tag/v3.10.4)
addon, pinned by commit and checksum. No Rust, GECS, model service, API key or
network connection is needed at runtime. Python tooling uses only the standard
library. Dependencies are downloaded once from public official sources.

Foundation's direction is a composable toolkit of independently optional modules
and pipelines for repeatable production across distinct games. Defaults and
templates are starting points; unique mechanics may need game-owned code. This
release implements the narrative subset listed below plus an experimental optional
[character-sprite art pipeline](docs/art.md) and independent
[scene navigation/depth primitives](docs/scene.md), independent
[audio controls/settings/envelopes](docs/audio.md), plus optional
[regression execution](tools/regression/README.md), [semantic replay records](docs/replay.md)
and [bounded narrative contracts](docs/narrative-contracts.md). Portraits, scene-art, UI/icons, VFX,
music asset pipelines and a replaceable Bevy backend remain future work. See the
[design decisions](docs/architecture.md#design-decisions) and
[contributor guardrails](AGENTS.md).

## Quick start

Requirements: Python **3.11+**, Godot **4.6.3**, and internet access for the first
pinned dependency fetch. The optional Godot installer below targets Linux x86-64;
on other platforms install the same engine version from
[Godot's official archive](https://godotengine.org/download/archive/4.6.3-stable/).

```sh
python3 scripts/fetch_dependencies.py
# Linux x86-64 only, if Godot 4.6.3 is not installed:
python3 scripts/install_godot.py
export PATH="$PWD/.deps:$PATH"

python3 scripts/prepare_example.py
godot --headless --path .build/village --editor --import
godot --path .build/village
```

The example is assembled into `.build/village`; open that folder in Godot. The
repository root is intentionally not a Godot project. The sample is clearly
marked as a **synthetic public approval fixture**, not a human-approved production
story. Its build explicitly opts into that fixture. Real projects use the manual
review/approval commands described in [authoring.md](docs/authoring.md).

In the village:

1. Talk to Mira before observing the bridge: she does not know the world fact
2. Inspect the bridge, then talk and share your observation
3. Talk again and mark the safe path: spend one chalk, gain a map and five coins
4. Talk again to hear the completed branch; save/load preserves knowledge and
   retry IDs

Trying to share before observing fails its command guard without changing state.
The UI uses Dialogue Manager for real line/response traversal; selections go
through the foundation's command bridge and transaction kernel.

## What is included

- Portable addon with deep-copy query/snapshot APIs and authoritative actor state
- First-match dialogue branches with fallbacks and guarded choice commands
- FIFO event/timer processing, deterministic rule ordering, rollback and retry
  deduplication; schema-1-to-2 save migration and fail-closed restore
- Structured scene/persona/context packets, provider-neutral generation request
  export and response import; an offline fixture requires no paid provider
- Strict IDs/references/conditions/effects checks, declared-claim knowledge guards,
  branch simulations and reviewer diffs
- Exact input/candidate/review hash binding, explicit manual approval and
  deterministic static JSON + Dialogue Manager builds
- Headless Godot regression tests, Python tooling tests, pinned public dependencies
  and read-only standard-runner GitHub Actions
- Deterministic addon bundle with upstream licenses and file hash manifest
- Independently optional rectangle sweep/slide/routing/reachable recovery and exact
  deterministic depth ordering; each script works without any other module
- Independently optional native audio bus creation, caller-owned level/mute
  preferences with explicit-path persistence, and stateless gain envelopes; no
  players, cues, assets, autoload or other-module dependencies
- Independently optional pixel-character art manifest, provenance/grid/palette/tag/
  timing checks, deterministic PNG/JSON export and optional Aseprite/Godot adapters;
  no AI provider/editor required for PNG input, no art runtime dependency

## Optional regression toolkit

The test-only Python runner wraps existing trusted commands with bounded execution,
strict JSON results, scenario inventories, diagnostic checks, lane status and
explicit coverage targets. The independently optional GDScript replay helper
records version/hash/seed identity, initial semantic state and action deltas.
Adapters own real execution and their oracle; no game framework migration or
narrative dependency is required. See [runner contracts](tools/regression/README.md)
and [replay contracts and synthetic example](docs/replay.md). The separate optional
[narrative-contract helper](docs/narrative-contracts.md) reuses replay canonicalization
for exact-state bounded BFS, authored required goals/options and shortest macro
counterexamples. Its neutral sample exercises real kernel/update/Label projection
boundaries and meaningful mutations. These tools are not automatic prose oracles,
general failure shrinkers, physical-input drivers or Web test harnesses.

## Optional impact-based test selection

The standalone [impact selector](tools/impact/README.md) plans trusted local suites
from an explicit Git base/head and a consumer-owned dependency map. It recognizes
whole-file allowlisted numeric-constant edits, expands shared dependencies and
falls back conservatively for unknown paths. Selection is not passing evidence;
unselected tests remain unclaimed. It does not add a runtime dependency.

## Optional durable source checkpoints

The standalone [checkpoint tool](tools/checkpoints/README.md) packs source and
authored assets, verifies a durable Library copy through a fresh restore drill,
and gates bounded work/phase transitions. It has no runtime module dependency.
A local commit or archive is never reported as a verified durable backup.

## Run checks

```sh
python3 -m unittest discover -s tools/regression/tests -v
python3 -m unittest discover -s tools/impact/tests -v
python3 scripts/test_replay.py
python3 scripts/test_narrative_contracts.py
python3 -m unittest discover -s tests/python -v
python3 -m unittest discover -s tests/art_godot -v
python3 scripts/test_art_godot.py
python3 scripts/test_scene.py
python3 scripts/package_scene.py
python3 scripts/test_audio.py
python3 scripts/package_audio.py
python3 scripts/fetch_dependencies.py
python3 scripts/prepare_example.py
godot --headless --path .build/village --editor --import
godot --headless --path .build/village --script res://tests/runtime/run.gd
godot --headless --path .build/village --script res://tests/runtime/test_dialogue.gd
godot --headless --path .build/village --script res://tests/runtime/test_consequence_contracts.gd
python3 scripts/package_release.py
python3 scripts/test_release.py
```

On a restricted Linux host, point `XDG_DATA_HOME`, `XDG_CONFIG_HOME` and
`XDG_CACHE_HOME` at writable directories before running Godot. The CI workflow runs
the narrative/art/release checks, standalone replay and bounded-contract checks,
and the native audio isolation/relocation runner
(including its deterministic package checks) on a standard Ubuntu runner. Scene
tests and scene-only packaging remain local verification for this proposal.
The opt-in exported Web-driver audio test is local-only. The workflow performs
no model calls, uses no secrets, and retains only `contents: read` permission.

For scene-only installation (no narrative, art or Dialogue Manager dependency),
contracts and the six-file deterministic bundle, see [scene primitives](docs/scene.md).

For audio-only installation, independently selectable scripts, persisted-format
contracts and the five-file deterministic bundle, see [audio primitives](docs/audio.md).
These runtime controls do not implement a music asset pipeline.

For standalone art usage, original synthetic fixtures and the optional licensed
Aseprite integration test, see [art subpipelines](docs/art.md). Character source
authoring and visual review remain manual. Real static and moving sources for a
second character have exercised the same export and consumer code. Gait approval
and game integration remain separate acceptance steps.

## Reuse in a game

`package_release.py` writes a ZIP and SHA-256 sidecar under `.build/releases`.
Unzip into your game project root; record the release tag/commit and archive hash.
It includes `addons/story_foundation`, the pinned `addons/dialogue_manager`, and
licenses. Enable Dialogue Manager in Project Settings → Plugins for its importer
and autoload. Foundation's runtime needs no editor plugin.

Your game owns its rules, approved content, UI and art. Keep raw authoring packets,
model responses and review records **outside your Godot project/export root**.
Only copy approved static runtime artifacts in. The example's staging script
illustrates that boundary; it does not copy review identities or source packets.

See [architecture](docs/architecture.md), [offline authoring](docs/authoring.md) and
[versions/upgrades](docs/versioning.md). A minimal runtime entry is:

```gdscript
const World = preload("res://addons/story_foundation/runtime/rule_kernel.gd")
var world = World.new()
world.configure(approved_content.world, approved_content.world.actors.size())
var fact = world.world_fact("bridge_closed")
var known = world.npc_knows("mira", "bridge_closed")
var result = world.dispatch_command({"id": "observation-001", "type": "inspect_bridge"})
```

## Deliberate limits

- No live LLM/API integration has been exercised. The request/response adapter
  boundary is real; the included generation response is a hand-authored fixture
- Validation checks declared claims and supported rules, not prose entailment,
  psychology, tone or missing annotations. Human review remains necessary
- Approval hashes detect edits; they do not authenticate a human or prevent a
  person with write access from forging/replacing a review
- No custom visual editor, arbitrary expression language, multiplayer server,
  high-volume ECS, automatic content migration or ledger compaction
- Linux headless import/tests and the native demo are the verification targets.
  Platform exports, export-template packaging and web/mobile compatibility are
  not claimed by this release; CI does not pretend to test them
- Content/save inputs are local trusted game data, not a security sandbox for
  hostile mods. See [SECURITY.md](SECURITY.md)

## License

First-party code and public fixtures: **MIT, Copyright © 2026 Derek Wang**.
Dialogue Manager and Godot retain their own MIT notices. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and `licenses/`; third-party code is
not relicensed under the first-party copyright.
