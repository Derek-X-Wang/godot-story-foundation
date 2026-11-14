# Optional portrait idle manifest and batch preflight

This v1 contract is independent of dialogue and the idle-host driver. The game
owns character art, timing, labels, review decisions and all manifests. Foundation
provides a structural preflight and a small Godot `MeshInstance2D` assembler for
one grid rig. Existing custom portrait adapters can declare `external` and keep
running unchanged.

## Manifest

Each JSON file describes one pose, not every appearance state of a person:

```json
{
  "schema_version": 1,
  "id": "neutral_pose",
  "base": "art/neutral.png",
  "canvas": [16, 16],
  "pose": "full",
  "review_tier": "batch",
  "rig": {
    "backend": "mesh_v1",
    "grid_px": 4,
    "pin_y": [2, 12],
    "breath": {
      "x_fade": [1, 3, 13, 15],
      "y_fade": [2, 4, 10, 12],
      "side": [8, 4],
      "displacement": [0.2, -0.2]
    },
    "elbow": {
      "pivot": [11, 10],
      "angle_radians": -0.05,
      "x_fade": [9, 10, 13, 15],
      "y_fade": [4, 5, 11, 12]
    }
  },
  "eyes": {"mode": "static"}
}
```

Coordinates are local source pixels from top left. Four-point fades are
`[start, full_start, full_end, end]`. `pin_y` leaves rows at and above its
first coordinate, and at and below its second coordinate, exactly at rest.
For a full figure, place the second pin above the legs and feet. The assembler
uses rest-space geometry, Foundation's GPU deformation include and a caller
supplied inhale phase; it does not generate a clock or move the root. The game
must pass a prevalidated manifest to `configure(record)`. The Godot assembler's
assertions catch basic dimensions and missing texture, but the Python preflight
is the required detailed data gate. If an elbow is absent, gesture weight is
zero. Do not mark the elbow present until an artist has registered its pivot and
fade through the connected sleeve.

An existing custom renderer can use `"rig": {"backend": "external"}`. Its
status is `adapter_only`; it is not assembled or motion-verified by this module.
Eyes use either `{"mode":"static"}` or `{"mode":"layered", "region":
[x,y,w,h], "half":"art/half.png", "closed":"art/closed.png"}`. The latter
requires matching canvas sizes and a separate registration review. A flattened
eye never becomes a blink or gaze layer by declaration. No mouth, age, body-state
or appearance-transition pipeline is implied.

## Batch gate and review queue

Run from a consuming project checkout:

```sh
python3 PATH_TO_FOUNDATION/tools/portrait_idle/validate.py \
  --project-root PATH_TO_GAME \
  --output PATH_TO_REPORT.json \
  PATH_TO_GAME/idle_manifests/*.json
```

The command exits nonzero if any record is `invalid`. It reads PNG headers for
existence, size and basic signature, checks path confinement, canvas and mask
geometry, and emits counts plus a centralized `manual_queue`. `machine_ready`
means structural preflight only; it is **not** visual approval. `adapter_only`
means the existing renderer remains responsible for motion checks. A static-eye
record remains in the queue with `eyes_static_no_blink_or_gaze`. A `main` tier
adds a named art-acceptance item. For side characters, review severe visual or
logical failures by sampling the batch and send only failures to annotation
or art repair. Record sample count, observed severe-failure fraction and minutes
per inspected/returned item before projecting throughput. Main cast requires
separate named visual acceptance. This tool does not claim a production yield
from its neutral fixtures or from one game's small sample.

Native rendered checks must additionally cover a complete cycle, pinned pixels,
seams and actual game lifecycle. PNG header checks do not decode complete image
data, assess layer registration, inspect identity or judge whether a gesture is
natural. Web export remains a consumer check when applicable.
