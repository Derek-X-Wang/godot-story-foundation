# Optional offline portrait local review

`tools.art.portraits.review` renders a **review-only** packet against exact PNG
source bytes. It is a small standalone adapter, not a portrait production
pipeline, semantic segmentation model, anatomy detector, art approval, or build
gate. It does not import the narrative runtime, sprite pipeline or Godot.
Python 3.11+ standard library is the only dependency. No network/model calls,
remote code, generated masks, credentials or model weights are required.

```sh
python3 -m tools.art.portraits.review \
  --packet /private/reviews/portrait-packet.json \
  --sources-root /private/portraits \
  --output /private/reviews/new-local-review
```

The output parent must exist; the output directory must not exist. Input source
files are read only, never repaired or replaced. A valid abstention packet is a
successful report, **not** an art failure. CLI errors (exit 2) mean malformed,
stale or unsupported input, not a defective character. Do not wire this command
into mandatory game builds or use its exit code to accept/reject art.

The report embeds source PNGs and contains potentially private imagery. Keep
inputs and reports outside game export roots and public source control. Source
asset rights remain the consuming game's responsibility. No private examples,
model code/weights or third-party art are shipped with Foundation. Unit fixtures
are generated neutral 2x2 pixels and first-party code follows the repository MIT
license. An upstream segmentation provider owns its dependencies, licenses,
model/data provenance and uncertainty; its accuracy is not certified here.

This is separate from the [registered-layer structural export gate](../tools/portrait_preflight/README.md).
That optional gate checks layer/import structure; this adapter only displays
review candidates and must not become an anatomy pass/fail gate.

## Input contract: `portrait-local-review-v1`

Top-level `schema`, `mode: "review_only"`, `automatic_approval: false`, `records`
(1..100). Each record contains:

- `name`: unique ASCII letters/digits/underscore/hyphen, 1..80 characters. Source
  resolves as `<sources-root>/<name>.png`; path traversal and symlink escape fail
- `source_sha256`: lowercase SHA256 of exact PNG bytes
- `source_size`: `[width, height]` matching the PNG IHDR
- `automatic_anatomy_verdict: null` and `projection_depth: "unobservable"`
- `status`, `pose_gate`, `semantic_gate`: descriptive strings, not approvals
- `regions`: 0..100 objects, each with finite `bbox_normalized_xyxy` in [0,1],
  strictly increasing x/y, plus strings `kind`, `reason`, `action`

Coordinates use the complete source canvas, top-left origin, x right/y down,
not an inferred body crop. Optional provider fields are ignored by the adapter;
only the listed contract is validated and displayed. The byte hash binds this
report to the image, not the truth of supplied regions. A caller must retain its
provider provenance and verify image/label correspondence. Input records are not
user approval records or authentication signatures.

The adapter reuses the shared bounded PNG codec (not the sprite pipeline) to
validate CRCs, chunks, decompression, filters and pixels. It accepts 8-bit RGB,
RGBA or indexed non-interlaced PNG only; no APNG or RGB+tRNS. Source limits:
20 MiB each, 100 MiB total, <=16384 pixels per axis, <=4,194,304 pixels each
and <=16,777,216 pixels total. Packet limit: 4 MiB. Images use lazy loading.
Valid decoding is not upstream alpha-quality, anatomy or rights validation. Report text is HTML-escaped; source
bytes are embedded as PNG data URLs, with no script or external resources and a
restrictive CSP. Output creation is exclusive and existing output is preserved.

## Output and limitations

- `report.html`: offline image, region overlays, statuses and review reasons
- `review-build.json`: exact packet/source hashes, counts, review-only mode

No automatic correction, source selection, approval invalidation, publishing or
runtime import occurs. This is separate from Foundation's hash-bound authoring
approval workflow and does not grant or replace its guarantees. All successful
reports prominently state that regions are review candidates, not defects, and
that 2D projection cannot establish 3D bone length. Short sleeve, occlusion,
foreshortening or exaggerated style may make upstream comparisons inapplicable.

The module can be omitted entirely. Other games/providers may supply their own
regions and reasons through the same narrow contract; they need not adopt any
particular segmentation model or character style.

## Tests

```sh
python3 -m unittest discover -s tests/python -p test_portrait_review.py -v
```

Tests cover standalone operation, abstention, provider extension substitution,
source immutability/hash changes, source dimensions, missing inputs, traversal,
outside-root symlinks, approval/depth rejection, invalid boxes, duplicate names,
escaped text, deterministic output and existing-output preservation. These are
adapter tests, not segmentation or anatomy accuracy tests. Run the full README
checks for repository regression coverage before release.
