# Optional art subpipelines

Foundation's art tools are **offline and independently optional**. The implemented
module is `character_sprite_v1`: a small pixel-sprite contract, checks, deterministic
export and optional Aseprite/Godot adapters. It does not require the narrative
runtime, Dialogue Manager, AI, an API key, or an editor for PNG input. The existing
runtime addon/package does not include or depend on these tools.

## Boundaries and status

| Subpipeline | Current status | Owns |
| --- | --- | --- |
| Character sprites | Implemented, experimental contract v1 | Authored frames → validation → atlas → optional Godot resources |
| Character portraits | Future, not implemented | Separate portrait source, crop, size and delivery contract |
| Scenes/environments | Future, not implemented | Separate tile/background/layer/placement contracts |
| UI/icons | Future, not implemented | Separate sizing, states and readability contracts |
| VFX | Future, not implemented | Separate timing, blending and effect contracts |
| Music/audio | Future, not implemented | Separate audio pipeline |

These are distinct selectable subpipelines, not required steps in one universal
art generator. A portrait and an in-game sprite may share a character identity,
but neither is automatically derived from the other or required to build it.
No empty plugin framework or universal humanoid rig is introduced for future work.

Shared code is deliberately limited: `tools/art/manifest.py` provides asset
identity, canonical records, source hashes and declared provenance checks;
`tools/art/png.py` provides a narrow pixel interchange codec. Character-specific
contract/pipeline logic is in `tools/art/characters`. Editor/runtime integrations
live in `tools/art/adapters`. Future modules should reuse only genuinely matching
contracts; they must not inherit pixel-sprite assumptions just to use provenance.

## Scene design: structure before detail

Use this optional game-owned design workflow before a scene's pixel/detail pass.
It is a human review recipe, not an implemented scene-art generator or a new
Foundation runtime contract.

1. **Establish purpose and context.** State who uses the place, what they do there,
   how they arrive and leave, and which environmental conditions matter. Give
   important structures and objects a function before assigning decorative shapes.
   Separate confirmed requirements from proposals that still need a decision.
2. **Draw the structure first.** Use a simple plan, blockout or perspective diagram
   with human-scale references, major masses, floor/water boundaries, entrances,
   activity areas and movement routes. Keep texture and small decoration out of
   this pass so scale, perspective, circulation and functional placement remain
   easy to change. Revise object placement and routes together before freezing
   collision rectangles, anchors or export layout; fitting every object outside
   an inherited walking rectangle is not a substitute for designing the place.
3. **Review function and physical relationships.** Check what supports each roof,
   platform and raised object, where surfaces meet, and what people can actually
   reach. A gangway should meet supported landing surfaces at both ends. A bench
   intended as a rain-sheltered waiting area needs suitable weather protection in
   that context; this is not a rule that every outdoor bench must have a canopy.
   Keep cargo, mooring fixtures and supports visually distinct. If a canopy is
   meant to be independent, show that relationship rather than accidentally
   turning it into another building. Review these meanings, not just empty-space
   clearance or plausible-looking outlines.
4. **Accept the structural version explicitly.** Before detailed native art, have
   the owner or designated reviewer inspect the diagram and record the version,
   decision and unresolved points. Do not infer acceptance from a passing test or
   the existence of a draft. Structural revisions need renewed review of the
   affected relationships; approval of a layout does not approve its final art.
5. **Add detail, then review at actual game scale.** Preserve the accepted spatial
   relationships while authoring editable semantic layers. Inspect both relevant
   layers and the composed view: an opaque background can hide unintended holes
   in a roof layer. Check that silhouettes, materials and contact cues still make
   objects readable with actors and UI present. Return to the structure pass when
   detail exposes a functional contradiction instead of disguising it with texture.

Palette, alpha, hashes, navigation and export checks establish their declared
technical properties; they do not approve architecture, shelter, object identity
or spatial logic. Keep this design review separate from
[drawing/input integration](scene.md#consumer-drawing-and-input-integration)
and record final visual acceptance explicitly as well.

## Quick start: no editor or game runtime needed

Python 3.11+ and its standard library are sufficient:

```sh
python3 -m tools.art validate examples/art/characters/narrow.json
python3 -m tools.art build examples/art/characters/narrow.json --output .build/art/narrow
python3 -m tools.art build examples/art/characters/broad.json --output .build/art/broad
```

Output must be a **new directory**. Existing builds and sources are never replaced.
Change the output name for another revision. Validation uses temporary storage and
does not publish a bundle. A failure leaves no partial output bundle.

Each build contains:

- `atlas.png`: canonical RGBA, fixed row-major grid, no scaling/trimming/rotation
- `atlas.json`: engine-neutral frame rectangles, timing, tags, cell and pivot
- `build-record.json`: source/manifest/artifact hashes, adapter version, declared
  provenance, warnings and machine-check results; **not an art approval**
- With `--godot`: `sprite_frames.tres` and `preview.tscn`

PNG bytes use deterministic uncompressed DEFLATE blocks. This trades file size
for byte reproducibility independent of compression-library versions. Game builds
may separately compress delivery archives without changing native pixel sizes.

## Manifest contract v1

See [the structural schema](../schemas/character-sprite.schema.json) and the small
[narrow](../examples/art/characters/narrow.json) /
[broad](../examples/art/characters/broad.json) examples. The CLI also checks the
cross-field and raster semantics that JSON Schema alone does not express.

- `schema_version: 1`, `kind: "character_sprite"`, stable lowercase `asset_id`
- `source`: `adapter` (`png` or `aseprite`), local relative `path`, exact `sha256`
- `provenance`: declared origin (`original`, `ai_assisted`, `licensed`, `unknown`),
  creator, license identifier/reference, rights status (`recorded` or `unknown`),
  and useful notes. Inputs are provider-neutral; no provider is invoked
- `cell: [width, height]`: native integer pixel size; no required 48×64 convention
- `pivot: [x, y]`: pixel-edge coordinates from the cell's top-left, x right/y down.
  The bottom edge may equal cell height. It is an attachment/origin convention,
  not proof of correct foot placement or foot locking
- `columns`: row-major atlas layout. Unused cells in the final row must be clear
- `palette`: 1–256 unique lowercase `#rrggbbaa` colors. Transparent pixels normalize
  to `#00000000`; all visible output colors must be declared. Indexed Aseprite
  source additionally requires exact native palette entries/order, including
  unused colors and order; animated palette changes are not supported
- `hard_alpha: true`: pixel-sprite v1 rejects partial alpha
- `tags`: explicitly ordered `name`, zero-based `start`, `count`, per-frame
  `durations_ms`, and `loop`. Tags partition every frame once, without gaps or
  overlap. Direction/state names are game-owned: four directions/six poses/walk
  state are not mandatory. Empty declared frames are rejected in v1

Limits: at most 4,096 frames, 1,024 pixels per cell axis, 4,194,304 atlas pixels,
64 MiB per source and 1 MiB manifest. Durations are integer 1–65,535 ms. The PNG
adapter accepts 8-bit non-interlaced RGB, RGBA or indexed PNG (indexed transparency
supported); other formats must be explicitly converted by a separate adapter.
It validates PNG structure/checksums and filters. This is not an untrusted-mod
security sandbox or a general image processing library.

The source lives beneath its manifest directory; absolute paths, traversal and
symlink escapes are rejected. The recorded SHA must match before processing and
after export. Review an intentionally changed source before updating its hash.
The tools do not write the native source, run a source-supplied script, regenerate
a rig, or silently repair failed checks.

### Provenance is evidence, not legal clearance

Unknown origin, unknown rights or unknown license fails closed by default.
`--allow-unknown-provenance` is an explicit exploratory override. It preserves an
`UNKNOWN_PROVENANCE` warning in the build record; it does not clear distribution.
Even a populated license is only an assertion: the tool cannot establish ownership,
consent, provider terms or legal permission. No approval label is minted by passing
validation. AI-assisted, hand-authored and licensed sources use the same checks.

Keep actual source art, prompts, receipts/licenses, approval records, masks and
rig/pose code in the consuming game's private authoring storage as appropriate.
Do not publish them merely because a generic pipeline is MIT. Treat the build
record as authoring/audit data: stage only chosen atlas/resources into the game's
export root when provenance notes are private. Source files/manifests are not
copied into the output bundle.

## Optional Aseprite adapter

Install/provide your own licensed Aseprite 1.3 executable. The repository does not
ship, fetch or require the editor. The tested version is **1.3.18.6**; other 1.3
versions pass the version gate but still require the integration test below.

```sh
python3 -m tools.art build /path/to/character/manifest.json \
  --aseprite /path/to/aseprite --godot --output .build/art/character-r1
python3 scripts/test_art_aseprite.py --aseprite /path/to/aseprite
```

This adapter reads existing `.aseprite` art via a Foundation-owned Lua inspector
and Aseprite's CLI sprite-sheet exporter. It compares cell/frame count, native
exposure durations, tags and untrimmed rectangles. Optional `source.layers` checks
an exact flattened hierarchy-order list; optional `source.pivot_slice` checks a
single constant full-cell slice with the declared pivot. Native tag playback must
be forward. Manifest `loop` is the intended consumer setting; Aseprite's finite
repeat count is not translated. RGBA sources check visible exported colors;
indexed sources additionally check every authored palette.

Authored layers remain editable in the untouched native source; the runtime atlas
is a deliberate composite. Hidden native layers are preserved but excluded from
the normal visible export. Source-specific masks, limb geometry, pose drawings,
cloth/prop motion, cleanup and anatomy review stay character-owned. This is an
export/validation adapter, **not** a way to generate a new body by stretching an
old character's rig.

The optional integration test constructs original RGBA and indexed native fixtures
from the public PNG drawings (including an unused palette color), then proves equivalent PNG/native atlas and Godot outputs, repeated
byte identity, source preservation, and rejection of native timing/tag/pivot/layer/
cell mismatches. It neither bundles nor downloads Aseprite.

Official references: [CLI](https://www.aseprite.org/docs/cli/),
[Sprite Lua API](https://www.aseprite.org/api/sprite),
[JSON Lua API](https://www.aseprite.org/api/json).

## Optional Godot consumer and preview

Add `--godot` to export a relocatable `SpriteFrames` resource and reusable
`AnimatedSprite2D` scene beside the atlas. Copy PNG and resource files together
into any Godot 4 project. No Foundation addon, singleton, importer plugin or
runtime script is needed. The scene autoplays the first tag at scale 1; place or
scale it in the consuming scene. It uses nearest filtering and sets its local
origin at the declared pivot. It does not decide movement speed, gameplay state,
collision, foot locking, animation speed multipliers or world pixel scale.

Timing is exact integer milliseconds (`speed=1000`, duration=declared ms), including
unequal exposures and loop/nonloop behavior. Relative references survive moving
the bundle within a project or into a fresh one. Godot may fill invisible RGB
beneath alpha zero during import; visible RGBA and alpha are verified exactly.

```sh
python3 -m tools.art build examples/art/characters/narrow.json \
  --godot --output .build/art/narrow-godot
python3 -m unittest discover -s tests/art_godot -v
python3 scripts/test_art_godot.py
```

The smoke test uses two clean projects and actually imports/loads/plays animations,
then deletes the first project and tests the relocated bundles. It covers original
independent serializer fixtures and both public manifests through the actual CLI.

## Reuse evidence and remaining manual work

The public fixture comparison exercises exactly the same pipeline implementation:

| Configuration | Narrow fixture | Broad fixture |
| --- | --- | --- |
| Native cell | 8×12 | 12×12 |
| Pivot | (4,11) | (6,11) |
| Frames / state | 2 / idle_down | 3 / work_down |
| Exposures | 160,240 ms | 90,130,210 ms |
| Loop | yes | no |
| Palette entries | 3 | 4 |
| Body / source | independently authored narrow geometry | independently authored broad geometry |

These are original MIT synthetic drawings, not production art or a claim of
universal anatomical reuse. The fixture generator is intentionally fixture-owned;
it is not a character-generation pipeline. Reuse means different source art and
manifest parameters pass the same validation/export/consumer code, rather than
copying hardcoded courier/stockkeeper scripts.

A private production source has also exercised the Aseprite adapter: 48×64,
24 frames across four six-frame walk tags, 16 indexed colors, (24,60) pivot and
120/120/240/120/120/240 ms exposures. Its layered source was preserved; none of
that game's artwork, rig/masks, prompts or private records is included here.

### Real second-character static reuse test

After concept approval, a separately authored broader, short-coat character was
normalized and cleaned up in its own private source. It ran through the exact same
committed pipeline and adapters without code changes:

| Actual source parameter | Existing walking character | Second static character |
| --- | --- | --- |
| Native cell / pivot | 48×64 / (24,60) | 48×64 / (24,60) |
| Authored frames | 24, four six-frame walk tags | 4, four single-frame idle tags |
| Native exposures | 120/120/240/120/120/240 ms | 1000 ms per static direction |
| Indexed palette | 16 entries | 20 entries |
| Editable layers | 6 | 3 |
| Character-specific art | Original long-coat/prop source | Independently normalized short-coat silhouette and face/hair cleanup |

Both used the same read-only native inspector, manifest checks, PNG normalizer,
Godot writer and consumer tests. Only source art and manifest parameters changed.
Repeated bundles were byte-identical, both source hashes stayed unchanged, the
existing walking character's atlas stayed pixel-identical to its previous export,
and the two characters passed **318 Godot checks in each of two fresh projects**,
including actual playback and relocation after deleting the original project.
No private sources, prompts, manifests, masks or review records are in this repo.

This closes the bounded **real second-character native static export and consumer
reuse** check. It does not establish reusable walk-pose synthesis across bodies.
The second character's silhouette selection, reference normalization, palette
selection, face/hair/coat cluster corrections and native-size visual review were
character-owned work. The first character's incompatible long-coat/prop masks
were not inherited. No universal rig was created, and no deployed game was
changed by this check.

### Real second-character moving-source reuse test

The second character's subsequent walk candidate also passed the same committed
pipeline unchanged. It has four forward walk tags with six authored poses each,
20 indexed colors, six editable layers, a 48×64 cell and (24,60) pivot. Its
140/140/280/140/140/280 ms exposures form a 1120 ms cycle, distinct from the first
character's 960 ms source cycle. These are native exposures; the pipeline does
not infer a game movement speed or apply a gameplay animation multiplier.

The final candidate was exported twice and compared with its original bundle:
all output files matched byte-for-byte and the source SHA stayed unchanged. It
and the original courier passed **478 shared Godot consumer checks in each of two
fresh projects**, including visible pixels/alpha, atlas rectangles, all tags,
nonuniform durations, pivot, nearest filtering, actual loop playback and relocation
after deleting the first project. The original courier atlas stayed pixel-identical.
No shared tool or adapter interface needed a patch for the moving source.

This establishes **real moving-character export and consumer substitution**.
The broader short-coat body's shorter limb geometry, moderate stride, masks and
pose drawing were still authored in its character-specific workspace. Generic
checks/export/import were reused; a universal rig or automatic motion synthesis
was not demonstrated. Character-owned geometric/contact checks are separate from
this module and cannot establish screen-space, subframe foot locking.

**Human gait approval and gameplay integration remain separate gates.** Successful
playback proves that declared frames and timing are consumed correctly, not that
the walk feels right or is ready to deploy. No live game was changed. Any later
source revision must update its manifest hash and repeat the checks and applicable
visual review at native and intended game scale.

The software checks do not assess style, anatomy, smoothness, grounded locomotion,
likeness or user approval. They establish technical artifact compatibility and
source preservation, not art approval or a promise that new characters are data-only.
