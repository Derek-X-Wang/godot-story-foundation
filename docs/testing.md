# Verification and release checks

The release targets Godot 4.6.3 and the pinned official Dialogue Manager 3.10.4.
Run the complete command sequence in the README after changes, including a fresh
project import. Python checks require no network or third-party packages.

## Consumer consequence and presentation contracts

Run `godot --headless --path .build/village --script res://tests/runtime/test_consequence_contracts.gd`
after the normal fresh assembly/import. This neutral test recipe uses the existing
kernel and the existing sample view; it adds no planner or runtime API.

- Clone the full authoritative snapshot, configure the same definitions and replay
  real guarded commands, inventory changes, costs and due timers. Compare every
  live state field before/after advisory queries, including retry receipts
- Share a game's actual effect/cost ordering. The synthetic negative control shows
  a commit started before a cutoff succeeds when effects precede its time cost;
  reversing them lets the real timer close the gate first. Foundation itself does
  not own a game's costs or make two dispatch calls jointly atomic
- Preserve the real operation-ID semantics. `ok` with `duplicate: true` may mean
  the required transition never happened. An accepted saved receipt is exercised;
  replacing/erasing it in a query is an explicitly failing design control
- Return unknown for simulation/restore errors, missing prerequisites, exhausted
  budget or no witnessed route. This recipe validates a proposed sequence; it is
  not a search algorithm and failure is not proof of impossibility. Partial probe
  state is never returned as a successful consequence. Cancel preserves live
  state; continuing through the same boundary reproduces the witness exactly
- Verify fact combinations in the real presentation path. Six synthetic recaps
  traverse the imported Dialogue Manager resource, real bridge and sample
  `_show_line` method, then assert the attached visible Label's final text. They
  cover failed primary work with completed secondary work, plus checked-but-not-
  shared versus unchecked results. These are headless UI-state assertions, not
  pixel-layout, browser, localization or human prose-review evidence

The existing native CI lane runs these cases and the extracted release repeats
them. The Python CI lane also runs the optional regression runner's self-tests,
including its real-process CLI final-report tests. A passing inner assertion count
alone is insufficient: final report status, process exit, complete logs and exact
selected evidence scope must agree. See the [consumer gate recipe](../tools/regression/README.md).

## Optional bounded narrative-contract checks

`python3 scripts/test_narrative_contracts.py` runs the independently optional
exact-state BFS helper in an isolated project, repeats it after fresh relocation,
and then exercises a separate native-kernel/attached-Label consumer. It uses the
existing strict regression runner for process, diagnostics and result evidence.
Author-supplied actions/goals remain independent of implementation catalogs.

Local verification on 2026-10-04 (Godot 4.6.3): **43 helper checks** in each
isolated/relocated project; **24 exact neutral states** and **9 exact kernel
states** within declared bounds, all required goals reached. Four valid-interface
mutations were caught: missing required option, defer lock, stale committed
projection and success text after command rejection. The latter preserves the
full authoritative kernel snapshot while changing an actual attached Label.
The unchanged fixed fixtures pass again; no game-private material is included.

Reports state the bounded scope, shortest macro traces, missing goals and state
limits. State-cap exhaustion is inconclusive; absent bounded witnesses do not
prove global impossibility. These are source/headless UI-state results, not
browser, pixel, packed-export or human narrative-review evidence. See the
[contract and author workflow](narrative-contracts.md). The hosted workflow runs
this runner and standalone replay; hosted success must be checked separately for
the exact published commit.

## Consumer content build and capture recipe

Use the applicable checks when a game adds runtime content. These are consumer
integration lessons, not new Foundation validators or extra mandatory CI lanes.

- **Cold generation:** generate into a fresh output directory with the pinned
  tools and compare emitted runtime bytes with the candidate. Include any later
  engine compilation; deterministic JSON or dialogue source alone does not prove
  deterministic engine resources. If serialization introduces a random resource
  identifier, fix only that understood, pinned adapter boundary, preserve all
  references and re-load/test the result. Broad text scrubbing can hide changes.
- **Real packed inputs:** build a fresh pack before checks and run affected
  behavior in both source and packed lanes. For newly loaded JSON or other raw
  assets, read their actual runtime paths inside the pack and compare hashes with
  source. An export filter that looks correct, a source-only pass or an old pack
  is insufficient. Native packed success does not establish Web execution.
- **Isolated execution:** give concurrent lanes separate writable user/config/
  cache paths and serialize shared import/export writes. Check the intended
  source inventory before and after; tests must not silently rewrite approved
  inputs. Record failures, blocked lanes and unrun checks explicitly.
- **Current-frame captures:** a headless label assertion proves UI state, not
  rendered pixels. On a rendered display, refresh the actual view and request
  redraw; if the harness suspended processing, temporarily restore what the view
  needs. Wait for its update and `RenderingServer.frame_post_draw` before reading
  the viewport texture, then restore the harness settings. Confirm the capture
  shows the intended state. A successful PNG write can still capture a stale
  frame; a rendered screenshot does not establish audible playback or art approval.

Keep timing evidence small: record content authoring/compilation, custom runtime
work, review/fixes, packaging and verification separately, with source identity,
tools, cache conditions and executed scope. Distinguish human/agent elapsed work
from command wall time; parallel intervals overlap and cannot be added as total
elapsed time. Without an equivalent baseline under matched conditions, report
observed durations rather than a percentage speedup. A fast focused check is not
evidence that unrelated suites ran or that an unfinished asset pipeline works.

## Verification records

Local optional-audio verification on 2026-10-03 (Godot 4.6.3): **8 focused Python
packaging/isolation tests passed**, plus **234 bus checks, 485 settings checks and
7,407 gain-envelope checks per project**, each repeated after removing the original
and relocating into a fresh isolated project without caches or UID sidecars.
The five-file module-only package is byte-deterministic and hash verified. Cases
include exact existing-bus preservation, append order, zero-level hard mute with
a −80 dB floor, old-format/missing-new-bus defaults, invalid values, persistence
failures and native smoothstep trajectories. See [audio contracts and limits](audio.md).
These are local native results, not hosted CI, browser listening or device
playback evidence. The existing public workflow now runs the native audio runner
and Python packaging checks with its already installed dependencies; its remote
result must be verified for the published commit. The opt-in exported-driver graph
test has separate inputs and remains local-only.

Local optional-scene verification on 2026-10-02 (Godot 4.6.3): **106 Python tests,
7 optional Godot serializer tests, 118 native runtime checks and 43 real Dialogue
Manager/native fixture checks passed**, plus 247 character-art checks in each of
two fresh projects. The full release ZIP imported and repeated its runtime,
dialogue and main-scene checks. No Aseprite binary was run for this change.

The new independent scene tests passed **4,823 navigation checks and 1,188 depth
checks per project**, each repeated after removal of the original and relocation
into a fresh isolated project. Scene-only packaging verifies an exact six-file
allowlist, deterministic bytes and manifest hashes. These checks use no narrative,
art, Dialogue Manager, autoload or asset dependencies. Cases include positive
sub-skin free channels, huge finite displacement safety and exact mixed numeric
ordering. See [scene contracts and limits](scene.md).

These scene checks are local-only for this proposal. The existing hosted workflow
is unchanged; integration and hosted verification are deferred to a separately
approved PR stage. No remote CI result is inferred from local success.

Prior local verification on 2026-10-01: **103 Python tests, 7 optional Godot
serializer tests, 118 native runtime checks and 43 real Dialogue Manager/native
fixture checks passed**. The extracted
release bundle repeats runtime/dialogue checks and imports cleanly. These are
local results; hosted CI is verified separately for the published commit.

Optional character-art verification on 2026-10-01 additionally passed:

- 247 Godot import/pixel/geometry/timing/playback checks in each of two fresh
  projects, including relocation after removing the original project
- 47 real Aseprite 1.3.18.6 CLI/Lua checks: two synthetic drawings plus indexed variant, PNG/native
  equivalence, deterministic output, source preservation and rejection paths
- Two private indexed character sources through the same committed pipeline:
  a 24-frame walk source and a different four-direction static source. Repeated
  exports were byte-identical and preserved both sources; the courier atlas
  remained pixel-identical to its existing approved export
- 318 Godot consumer checks in each of two fresh projects for those real sources,
  including actual import/playback and relocation after removing the first project
- The second character's subsequent 24-frame walking source through the same
  unchanged exporter, alongside the original courier: 478 Godot checks in each
  of two fresh projects, including nonuniform timing, loop playback and relocation.
  Repeated outputs match its final candidate bundle byte-for-byte; both sources
  and the existing courier raster are preserved

The public CI runs PNG/manifest tests and the standalone Godot consumer tests.
It does not install a licensed Aseprite binary; run the documented optional test
locally. Second-character static and moving source export/consumer reuse is now
exercised. Character-specific pose/rig authoring, human gait approval and gameplay
integration remain separate responsibilities; raster/consumer checks do not grant
art approval or prove universal rig reuse.
See [art checks](art.md).

Coverage includes:

- The original 46 native rule regressions, then portable APIs, copied queries,
  generic inventory/scenes, guarded commands, declared save facts and numeric bounds
- Actual Dialogue Manager import, conditional line/response traversal, choice
  mutations, stale/repeated buttons, resource cleanup, and replay of the same
  declared fixtures used by the Python simulator
- Packet/candidate/reference validation, missing fallback and branch coverage,
  safe DSL generation, input/candidate/review mutation invalidation, synthetic
  fixture opt-in, deterministic builds, and schema/CLI failure cases
- Download size and checksum validation, ZIP path/symlink rejection, package
  allowlisting and deterministic archives

A Linux cloud-desktop walkthrough exercised honest ignorance, unavailable choice,
private observation, shared knowledge, path marking and reward, then save,
restart and load. Headless startup independently checks the main scene. These
checks do not establish a frame-rate target or portability to another OS.

Before publishing a release:

1. Run all checks against the exact final source
2. Rebuild twice and compare archive bytes and SHA-256
3. Inspect the package manifest and extract/import it in a fresh project
4. Confirm authoring/review data, caches, binaries and credentials are absent
5. Verify the hosted CI run for the published commit, rather than assuming local
   success proves remote CI
6. Record the source tag/commit and package SHA-256 in consuming games

Not run by this repository's CI: paid/live model generation, production human
review, export-template builds, platform exports, web/mobile execution or networked
multiplayer. Review approvals use exact file hashes and explicit CLI affirmation;
the synthetic test fixture is not evidence of a human reviewing production prose.
