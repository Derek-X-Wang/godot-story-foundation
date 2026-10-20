# Production starter and review-record gates

Use this as the default starting workflow for a new game, before copying the
village demo's presentation. It is a small **offline Python 3.11+ tool**, not a
runtime module, game generator, physics engine or visual-quality detector.
A project can deliberately replace it with an equivalent game-owned process;
record that choice rather than silently losing its checks. Existing independent
runtime modules remain usable without it.

## Start, then work at the appropriate stage

```sh
python3 tools/production/production.py init --output ../my-game
cd ../my-game
python3 tools/production.py check authoring/production.json --gate flow
```

The last command initially fails with the first missing decision. Fill `project`,
`scope`, `revision` and `references.flow`. Flow prototyping can then proceed without
art approval. The starter never overwrites an existing workspace. It creates:

- `AGENTS.md`: concrete startup, composition and completion instructions for the
  next contributor/agent, including spatial, dialogue and visibility review.
- `authoring/production.json`: a game-owned brief and pending review records.
- `tools/production.py`: the same portable checker, with no Foundation checkout,
  packages, engine or network required after relocation.
- `game/`: the intended runtime/export root, separate from authoring and evidence.

Install the runtime modules you choose into `game/`. The existing
`prepare_example.py` still assembles the synthetic village demo; it is not a new
production game's creative template. For an existing game, inspect its instructions
first and explicitly adopt the brief/checker without overwriting its AGENTS.md.

| Gate | Required before claiming this stage |
| --- | --- |
| `flow` | Project/scope/revision and the semantics-only flow reference |
| `brief` | Deliberate reference roles, presentation convention, scale/contact/continuity, movement, UI/visibility, viewports and representative states |
| `composition` | Brief, selected asset maturity, explicit scoped review and current rendered candidate evidence; stand-ins may be accepted for composition only |
| `integration` | Composition prerequisite, accepted in-scope assets, current composed candidate review and applicable focused checks |
| `release` | Earlier prerequisites, current final-candidate rendered review and all declared applicable final check lanes passed |

A populated field is only a recorded decision. A reviewer must assess the actual
[spatial relationships](../../docs/art.md#representation-aware-spatial-coherence)
and [rendered checks](../../docs/testing.md#consumer-spatial-and-motion-review).
`symbolic_grid`, `scene_perspective` and `custom` are conventions, not quality
rankings. Explain justified non-applicability in the text fields. UI portraits
have a separate role from world actors; no visual-novel, fullscreen, walk-cycle or
strict-realism format is mandatory. `references.*` declares `kind` (`local`, `external` or `none`), `source` and
`identity`. Local sources use an authoring-relative path and verified SHA-256;
external sources use an immutable version/hash identifier (not fetched). Use
`kind: none` only with `status: not_applicable`. `use` says what it establishes, including a reason when
`status` is `not_applicable`. References are declarations, not fetched resources.

Runnable neutral brief examples (synthetic, **no visual acceptance**):

```sh
python3 tools/production/production.py check tools/production/examples/symbolic-rpg.json --gate brief --allow-test-fixture
python3 tools/production/production.py check tools/production/examples/perspective-scene.json --gate brief --allow-test-fixture
python3 -m unittest discover -s tests/python -p test_production_workflow.py -v
```

## Record a real review

Keep captures/logs beneath `authoring/`, for example `evidence/room-entry.png`.
Review entries have `decision` (`pending` until explicitly accepted), `reviewer`,
`reviewer_kind` (`human` or `agent` in production), `reviewed_at`, the exact accepted `scope`,
`candidate_revision`, `candidate_sha256`, `evidence`, `checks` and `basis_sha256`.
Do not label agent review as owner/human approval. Use the game's actual review
policy; this tool does not require the owner to approve every routine step.

Each evidence entry has `path`, file `sha256`, `kind`, `scope`, `platform`,
`viewport`, `route_state` and the `candidate_sha256` captured at execution time. Paths are relative to the record's directory. Kinds:

- `rendered_still`: actual current game frame, not an isolated asset or mockup.
- `rendered_sequence` or `playback`: actual motion/cut/transition evidence. Any
  movement mode except `none` requires one of these, not endpoint stills alone.
- `check_report`: technical results, never a substitute for rendered evidence.

Visual entries must cover every declared viewport/state pair, including dialogue
under each target framing. Choose representative states narrowly and explicitly.
One genuine sequence can be referenced for multiple targets it actually shows;
duplicate artifact/target entries are rejected. An evidence entry's candidate
fingerprint must match its containing review. Updating a review's identity never
rebases old evidence automatically. Check-report viewport/state can say
`not applicable`.

`checks` entries contain `name`, `result` and `evidence_path` pointing to a hashed
`check_report`. Record failed, blocked and unrun lanes honestly: they block gate
closure. List all applicable lanes for the declared scope; the checker cannot
infer missing tests. Do not omit failures merely to make a green record.

Use `identity` once when capturing/running checks to record the current candidate
fingerprint with each artifact. This first call need not have a finished review.
After inspecting the candidate and evidence, fill the real reviewer, reviewer kind,
reviewed-at time, scope, evidence and checks; then obtain the final binding values:

```sh
python3 tools/production.py identity authoring/production.json --gate composition
```

Copy the returned `candidate_revision`, `candidate_sha256` and `basis_sha256` into
that review. Record the actual decision, then run `check --gate composition`.
Changing reviewer metadata afterward invalidates the binding too. Repeat for integration/release only at those stages. `identity`
is read-only: it never approves, repairs, executes a check or edits a record.
Never refresh hashes to conceal changed work; inspect and review it first.

The candidate path is workspace-relative, normally `game`, and must exclude the
authoring directory. Its digest includes every regular file's relative path and
SHA-256, including dirty/untracked files, except `.git` and `.godot` directories.
Freeze the candidate while checking; do not put unrelated logs/caches there.
Include the actual built deliverable in this tree when claiming that build was
reviewed; hashing source does not prove an external pack/browser build matches it.
No external build path is covered implicitly. Symlink inputs are unsupported.

Brief/policy or evidence changes invalidate affected bindings. A previous
composition review remains a historical direction prerequisite after source
changes; it does not replace the new integration/release candidate's own rendered
review. Earlier evidence must remain available. Final asset status must be accepted
for the declared integration/release scope; name excluded or unfinished work in
`scope`, rather than calling an unfinished whole game released.

## Trust boundary and verification

Success means **declared record/evidence prerequisites are satisfied**, not
"the scene is physically correct". Hashes detect changed bytes, not authenticity,
rights, honest reviewers, actual runtime provenance, physical input, visible pixels
or a person's understanding. A mislabeled text file can still have a valid hash.
Human/agent inspection remains necessary, and machine checks cannot approve art.
Hidden/offscreen samplers and headless assertions are not eligible rendered kinds.
Synthetic fixtures require an explicit opt-in and cannot pass production by default.

The tool is read-only except for explicit fresh-workspace initialization. It runs
no supplied commands. Tests run in the existing Python CI lane, covering the
scaffold, relocation, stage boundaries, both representation examples, stale input
and evidence rejection, eligibility, asset maturity, paths and malformed records.
The normal Foundation runtime/release suites remain unchanged and independent.
