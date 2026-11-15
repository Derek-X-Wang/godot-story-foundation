# Optional registered-layer portrait adapter (experimental)

`addons/story_foundation/presentation/registered_portrait.gd` is an independently
optional Sprite2D adapter for **already registered** full-body texture layers.
No generator, network service, character name/path lookup, automatic segmentation,
rigging, story state or human approval record is included. Games own their art,
registration coordinates, review and export policy. Do not put private portraits
or character-specific configuration in Foundation.

## Contract

Call `configure(definition, layers) -> bool` before use. Definitions are copied;
callers own Texture2D lifetimes and must not mutate shared texture contents during
playback. Configuration failure retains the previous valid state. Unconfigured
nodes stay dormant. Successful configuration resets clock and pause state.

Definition fields:
- `width`, `height`: positive integer pixel dimensions shared by all layers (maximum 16,384).
- `sourceHeight`: registration height in [0.001, 1,000,000]; all
  registration coordinates/radii are bounded to 1,000,000 and scale uniformly by `height/sourceHeight`.
- `chest`, and two `eyes`: `[center_x, center_y, radius_x, radius_y]` ellipses (radii >= 0.001).
- Two `eyeRegions`: `[x, y, width, height]` registered gaze clipping rectangles (width/height >= 0.001).
- `breathing`: `amplitude` in [0, 1000] and `periodSeconds` >= 0.001.
- `blink`: sorted nonoverlapping `starts`, `closeSeconds`, `holdSeconds`,
  `openSeconds`, each >= 0.001. This version uses an explicit **8-second loop**; each blink must
  finish within it. It is an optional schedule template, not physiology.

Layer dictionary keys (Texture2D, same dimensions): `base_tex`, `half_tex`,
`closed_tex`, `plate_tex` (clean eye plate), `iris_tex`, `mask_tex` (eye aperture).
The shader samples registered RGB and alpha channels; iris import must preserve
its authored soft-edge RGB. For PNG iris imports set `process/fix_alpha_border=false`.
Do not indiscriminately disable border correction on the full portrait. Wrong
import settings can pass structural checks yet alter visible eyes. The adapter
does not inspect import metadata or automatically repair source layers.

`sample(seconds)` chooses absolute time; `advance_motion(delta)` advances unless
paused. `pause_motion()`/`resume_motion()` control playback. Invalid time is ignored.
The root is never animated/rotated. Breathing is masked to the supplied chest
ellipse; consumer registration must keep feet outside it. Eye gaze uses the
included 8-second hold/ease template and 2.5 source-pixel horizontal extent.
These defaults are explicit limitations of this initial adapter; consumers can
replace the schedule/shader instead of changing story/runtime modules.

## Verification scope

Neutral tests use generated solid-color textures and no private source material.
They cover configuration, dimensions, copied definitions, failure preservation,
lifecycle, pause/resume, blink and breathing parameters. They do **not** prove
naturalness, automatic layer creation, scene composition, per-character pinned
feet, Web/mobile support or throughput for a thousand characters. Each consuming
game must test its registered artwork and target renderer. Capture outputs may
use premultiplied alpha; compare them with correct compositing semantics rather
than double-multiplying alpha.

Run the neutral suite without downloaded dependencies:

```sh
python3 scripts/test_registered_portrait.py
```
