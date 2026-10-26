# Optional static resource review adapter

Python 3.11+ standard library builds a static website; a browser displays it. No
Godot, editor, server, account, model, CDN, database or runtime module is required.
This is a **read-only review surface**, not a new asset canon, generator, editor,
CMS, feedback inbox, publishing service or approval authority.

It displays selected character/scene PNG stills and plays the existing
`character_sprite_v1` `atlas.json` frames/tags. Scene authoring is still not an
implemented Foundation art pipeline. The adapter does not turn a scene into a
sprite contract. It just displays its chosen PNG. Animated previews use authored
integer millisecond durations and loop flags; start paused, support frame stepping
and stop on hidden-document/focus loss. Browser scheduling is not engine playback
or proof of gait quality. No sound is included.

## Working neutral example

From the repository root:

```sh
python3 -m tools.art.preview.example --output .build/resource-review-r1
# Open .build/resource-review-r1/site/index.html in a browser.
```

This builds both existing original public character fixtures through the existing
art pipeline, then passes their atlas output unchanged to the viewer. Whole-sheet
stills exercise character and scene viewing without inventing new art; their labels
explicitly say they are sprite-sheet stand-ins, not production scenes. The site
can be opened locally or copied to an approved static host. Nothing is deployed by
this command. Source/build records remain outside `site/`.

## Consumer-selected index, not another asset database

Use IDs from the consumer's existing asset inventory (and the exact `asset_id`
from character `atlas.json`). Make this small view selection beside the selected
files; no asset renaming or schema migration is required:

```json
{
  "title": "Candidate resources — review only",
  "assets": [
    {"asset_id": "room_north", "label": "North room", "kind": "scene",
     "image": {"path": "selected/room.png", "sha256": "<actual PNG SHA-256>"}},
    {"asset_id": "courier", "label": "Courier walk", "kind": "animation",
     "image": {"path": "selected/courier/atlas.png", "sha256": "<actual PNG SHA-256>"},
     "atlas": {"path": "selected/courier/atlas.json", "sha256": "<actual JSON SHA-256>"}}
  ]
}
```

`kind` is `character` or `scene` for a still, `animation` for an existing character
atlas. Paths are local relative files beneath the index directory; supplied hashes
must match. Build with:

```sh
python3 -m tools.art.preview.build authoring/review-index.json --output .build/review-r2
```

Output must be new; previous versions are never overwritten. Validation checks
PNG structure, atlas identity, bounds, ordered tag coverage and timing; a failed
build promotes no site. The narrow PNG codec has the same format limits as the
[existing art pipeline](../../../docs/art.md). Only selected PNGs, playback
metadata, public labels/IDs and viewer files are copied. It deliberately excludes
source paths, build-record provenance notes, prompts and native editable sources.
Review the selected bytes and public labels before publishing; this adapter does
not determine their rights. PNG bytes are copied unchanged, including ancillary
metadata; review/remove sensitive embedded metadata in the selected source before
building. Neither pixel contents nor embedded prompts/comments are sanitized.

Version is SHA-256 of the canonical image hash + selected playback data, not a
mutable display label. The same asset ID may appear at different versions; duplicate
ID/version pairs fail. PNG or timing changes produce a different version; editorial
label changes do not. `preview-build.json` hashes delivered viewer/catalog/image
files and is an artifact record, **not acceptance or a source checkpoint**.

## Browse → locate → report → revise

1. Choose a resource and animation tag. Play to inspect motion; pause or step to
   the relevant zero-based frame. Choose pixel scale without changing source size.
2. Click the relevant pixel. Coordinates are frame-local (or whole-image for a
   still), not CSS-screen coordinates or an atlas offset.
3. The direct link includes exact asset ID, full version, tag, frame and optional
   pixel coordinates. A missing version/tag/frame fails closed rather than silently
   showing a different asset. Retain old immutable preview versions for old links.
4. Enter the requested change, prepare feedback, copy the text and send it through
   the project's existing conversation/issue/review channel. Clipboard fallback
   selects the text for manual copying. **There is no submission or persistence.**
5. The implementer resolves that asset/version in the consumer inventory, edits
   its actual source, rebuilds a new version, then replies against the original
   feedback with a new link and the outcome. Preserve the old link; do not silently
   retarget comments. For motion, include the relevant frame range/observed timing
   in the free-text request; a single frame does not establish motion quality.

Use a hosted URL when sharing: a `file://` link identifies only your own machine.
Feedback text includes exact version/location even when a link cannot be opened.
The existing production evidence and scoped approval mechanisms remain authoritative;
resource preview is not full composed-game, route, story or emotional acceptance.

## Safe hosting and durable handoff

- Keep the approved game's root and candidate/resource previews at distinct,
  clearly named paths, with a visible candidate label and direct navigation links.
  Adding a preview must not replace the approved root. Compare retained root file
  hashes before and after host packaging; verify actual root and preview URLs.
- Paths on one site share an **origin**, not a security or storage boundary.
  This viewer uses no storage or service worker, but sibling game exports may.
  Check their storage keys, engine persistence mounts, cache/service-worker scope
  and actual browser behavior. Separate origins or deliberately isolated consumer
  storage may be needed. Disabling an engine persistence mount is not proof that
  every other storage channel is isolated. Never present static checks as tested
  browser isolation.
- Before expensive QA, approval waits, publication or changing workspaces, preserve
  exact editable sources, tests, build inputs and raw evidence using the existing
  [durable checkpoint loop](../../checkpoints/README.md), or a named equivalent
  with independently verified off-workspace recovery. An unpushed commit, live
  website, exported PCK/ZIP or preview-build record is not an editable source backup.
  Keep private game materials in their authorized private destination.
- If only a compiled candidate survives, mark source recovery unavailable. Do not
  claim it can be rebuilt from a runtime hash or reconstruct missing source from
  assumed intentions. Keep surviving runtime and QA evidence separately labeled.
- Preserve pending evidence honestly: source/static assertions, actual browser
  controls/frames, listening and aesthetic acceptance are different results. A
  candidate with passing packaging checks may still have untested browser storage,
  short animation or audible behavior. No acceptance label is generated here.

## Checks

```sh
python3 -m unittest discover -s tests/python -p test_art_preview.py -v
node tests/art_preview/test_viewer.cjs
# Optional browser smoke; provide installed dependencies, no auto-install:
PYTHONPATH=. python3 tests/art_preview/browser_smoke.py --chromium /path/to/chromium --report .build/preview-browser.json
```

Python checks deterministic output, hashes, identity, malformed data and nonleaking
metadata. Node checks authored timing, strict deep-link resolution and feedback.
The optional real-browser smoke checks controls with neutral fixtures; it is not
artistic acceptance, supported-device certification or a hosted-origin isolation
test. Missing dependencies or blocked browser execution remain unrun, not passed.
