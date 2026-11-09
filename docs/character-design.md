# Optional character-design provenance

This is a small offline record checker, not a generation pipeline. It depends only
on Python 3.11+ and `tools/art/manifest.py`; it needs no pixel pipeline, model,
editor, engine or network. Run it as `python3 -m tools.art.design` from the repository
root. Consumers may copy `tools/art/{__init__,manifest,design}.py` together and use
the same command from their own root. Keep records and sources in private authoring
storage outside the runtime/export tree. The runtime package is unchanged.

## Stages and acceptance

| Stage | Purpose and what to retain | Separate acceptance question |
| --- | --- | --- |
| Concept (`concept`) | Explore identity, silhouette, clothing and visual direction. Direct image generation or hand drawing is valid; retain the actual concepts, selected version and intentional alternatives. No body-reference tool or design sheet is a prerequisite. | Has the owner/designated reviewer selected this direction for this character and revision? |
| Design (`design`) | Resolve the selected direction into useful views, expressions or detail sheets. Retain the selected concept and identify each reference's role. View counts and medium belong to the game. | Are identity, intended details and cross-view consistency acceptable for the stated use? |
| Pose study (`pose_study`) | Explore a particular pose, camera or body reference; record the actual sources and known limits. It may inform a design without replacing the concept. | Is this pose/camera useful, and which anatomy, identity or geometry claims remain unverified? |
| Runtime asset (separate contract) | Prepare the game's selected portrait, sprite or other delivery format. Record its link to design sources and intentional adaptations. | Does the asset satisfy its own delivery contract, and does it read and behave correctly in the actual composed game? |

These are useful distinctions, not a compulsory linear sequence. A concept remains
a first-class deliverable; it is not discarded when a design or pose study is made.
Concept selection, design acceptance, runtime compatibility and game integration
are different decisions. A successful provenance check is neither art approval nor
integration approval. Use the existing [production gates](../tools/production/README.md)
for flow, brief, composition, integration and release; this optional record does
not replace or automatically close any of them. An accepted concept does not
approve a derived asset or its rendered scene.

Nvwa is one optional, replaceable source of body/pose reference. It is not a
required provider, the final character, or a guarantee of identity, anatomical or
geometric consistency. No provider-specific parameter mapping is implemented here.
A retained reference hash establishes which supplied bytes were used in the record,
not that a renderer honored them. Evaluate alternatives under the same intended
scope and preserve unresolved limits instead of freezing an unverified pipeline.

## Small record contract, version 1

The executable contract is [design.py](../tools/art/design.py); the completely
synthetic [record](../examples/art/design/record.json) uses two hand-authored SVG
geometric markers. It is not a visual-quality or human-approval fixture.

- `schema_version: 1`, `kind: "character_design"`.
- `character`: logical lowercase `id` and nonempty string `revision`. The caller
  supplies an independent expected ID and revision; the tool compares them exactly.
- `stage`: `concept`, `design` or `pose_study`. Runtime assets use their own contract.
- `references`: zero to 32 `{role, path, sha256}` entries. Roles are game-owned
  lowercase identifiers, e.g. `concept`, `style`, `body`, `pose`. Zero references
  permits direct concepts or work with no retained source file; it does not prove
  reference-free generation. Record omitted evidence in `limitations`.
- `producer`: recorded generator/renderer/editor `name` and `version`. Optional
  `model` and `work` each have opaque `id` and `revision` strings. Omit unavailable
  metadata and describe that limit; do not invent a model version or Work identity.
- Optional `capture`: nonempty object containing `camera` and/or `pose` descriptions.
  Include conventions/units where relevant. These are bounded text declarations,
  not portable parameter mappings or validated camera/pose geometry.
- `output`: one `{path, sha256}` for the actual design artifact. Use separate records
  for separately reviewed outputs. There is no rendering or output promotion step.
- `limitations`: one to 32 explicit nonempty statements about known gaps and scope.
- `review`: `status` (`pending`, `accepted`, `rejected`), `reviewer`, `notes`,
  `basis_sha256`. Pending requires null reviewer/basis. A recorded human decision
  requires a reviewer string and a matching basis. `notes` states the review scope.
  Never label an agent evaluation as human acceptance.

Unknown fields, duplicate JSON keys, wrong types and unsupported versions fail.
The shared reader limits JSON to 1 MiB and text to 4,096 characters. Each referenced
or output file must exist beneath the record directory and be at most 64 MiB.
Paths are relative, using `/`; absolute paths, empty/dot/traversal segments,
backslashes, colons and symlink escapes fail. Duplicate resolved reference/output
paths fail too. Internal symlinks follow the shared source-path policy. Freeze
local files during a check; this is not a concurrent filesystem security sandbox.

The checker reuses exact SHA-256 byte comparison from `tools/art/manifest.py`.
It does not decode images or require PNG, palettes, hard transparency, frame sizes,
rigs or a body type. A hash-valid text file can pass: artistic meaning and even
file-format correctness are outside this check. Pixel constraints remain exclusive
to [the pixel-character contract](art.md#manifest-contract-v1).

## Reproducible checks and human review

```sh
python3 -m tools.art.design examples/art/design/record.json \
  --character-id sample_marker --revision draft-1
python3 -m unittest discover -s tests/python -p test_art_design.py -v
python3 -m unittest discover -s tests/python -v
```

Success reports local hash agreement and the declared human review status; pending
and rejected records can both be structurally valid. This command is not an
acceptance gate. It exits 1 on validation/I/O failure and never writes a record,
source, output or approval. A wrong `--revision draft-2` must fail.

For a real human review, first check a pending record, inspect the actual artifact
and its references, and retain the returned `review_basis_sha256`. Only after an
actual decision should the consumer record `accepted`/`rejected`, the real reviewer,
scoped notes and that digest as `review.basis_sha256`. The basis hashes the shared
canonical JSON representation of every field except `review`. Any change to
identity, stage, sources, producer, capture, output or limitations invalidates the
binding. The tool never silently refreshes it. Retain historical review records;
reviewer assertions are audit evidence, not authentication signatures.

For stronger correspondence checks, pass a previously retained independent record
digest from the intended source/candidate or review evidence:

```sh
python3 -m tools.art.design path/to/record.json \
  --character-id sample_marker --revision draft-1 \
  --expected-record-sha256 "$EXPECTED_RECORD_SHA256"
```

That pin covers the exact record bytes, including reference roles, source/output
hashes, metadata and review assertions. The expected identity/revision should come
from the consuming game's intended character, not be copied blindly from the
record under test. Without the optional independent pin,
`record_matches_independent_expectation` is false: local self-consistency alone
cannot catch a changed file plus a matching rewritten hash, a wrong reference
role, or an intentionally swapped source/output mapping. Computing a new expected
digest from that same suspect record is not independent evidence. Even a matching
independent digest does not establish the semantic truth of the pinned claims.

`semantic_correctness` and `remote_persistence` always remain `not_verified`.
There is no provider request, remote read-back or durable-storage verification.
`art_approval` and `integration_approval` remain `not_determined_by_tool` regardless
of the recorded status. Rights, provenance authenticity and reviewer identity
also need separate evidence; this record supplies no legal clearance.

## Deferred animation boundary

Animation control code and each character's mouth/mask calibration have separate
ownership. Logic tests, actual rendered behavior and user acceptance are different
evidence. A fair comparison remains pending; this change selects no animation
backend and implements no animation framework.

Record portrait performance under [character portraits: idle and talking](character-portraits.md).
That design guide covers blinks, resting versus talking mouth behavior, selected
chest/torso breathing emphasis and separate visual review for every character.
It preserves intentional character differences and does not extend this provenance
checker's schema or turn its byte checks into animation approval.
