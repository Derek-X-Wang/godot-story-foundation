# Optional idle-host driver

Godot 4.6.3 built-ins only; no narrative, art, audio, plugin or autoload dependency.
This is a visibility/pause/clock adapter, not an animation generator or portrait UI.
Consumers own characters, geometry, phase/amplitude, timing and visual acceptance.

## Contract
Add the driver to the tree, then attach an already-ready Node2D implementing
resume_motion(), pause_motion(), advance_motion(delta). The last method must
respect its paused flag. Attachment validates these methods, but cannot prove
their semantics. Calls are synchronous; do not attach reentrant/untrusted scripts.
Only one driver may own a portrait; a WeakRef metadata marker rejects a competitor.
It disables the portrait's own process callback. Do not enable that callback or
alter the ownership marker while attached. Driver and portrait lifetimes are
caller-owned: no reparenting, scene edits, freeing or persistence is performed.

Set host state explicitly with started, paused, backgrounded, conversation_visible,
and ending_visible booleans. Idle runs only if started and conversation-visible,
not paused/backgrounded/ending-visible, and portrait visible in the scene tree.
The driver checks visibility every tick. This is not viewport culling, application
focus detection, modal detection, or scene-tree pause bypass. Its inherited process
mode follows Godot defaults. Consumers translate their own states into these flags.

Use either automatic _process or set_process(false) and call tick(delta) yourself,
not both. Invalid/nonpositive deltas are ignored. Hidden/paused time is not accrued;
resume does not reset phase. Detach pauses idle, restores the pre-attachment process
flag and releases metadata, but does not restart animation. Driver exit detaches.
A freed portrait is tolerated. Call detach before reconfiguring lifecycle/ownership.

The driver cannot advance dialogue, game time, choices or saves. It has no speaker
mapping, text reveal, UI controls, asset loading or fixed body-region assumptions.
Games may replace it with another policy without changing narrative modules.

## Standalone check
Run the synthetic tests in a temporary Godot project containing just the driver and
tests/portrait_idle/test.gd. The test fixture draws no image and uses no private art.
The tests cover all 32 host flags, hide/show, invalid input, ownership, lifetime and
return of original true/false process flags. Passing them is not visual approval.

## Optional motion primitives

`addons/story_foundation/presentation/portrait_idle_motion.gd` is a stateless,
independently optional `RefCounted` utility (Godot 4.6.3 built-ins only). It can be
used without the driver or narrative systems. It does not load art, attach nodes,
move the root, own a clock, serialize state or generate masks/rigs.

- `breath(cycle)` gives a smooth 0 → 1 → 0 inhale weight for a cycle measured in
  turns. The host/portrait chooses a positive duration and advances the clock.
- `deform_point(rest, inhale, displacement, pivot, angle_radians, weights, pinned)`
  composes rest-space breathing displacement with a pivot gesture. The two
  weights independently control breathing and gesture, clamped to [0, 1]. A pin
  overrides both exactly. Always start with the original rest point, never last
  frame's output. Coordinates, offsets and pivot use the same local units.
- `blink(elapsed, duration, has_eyelid_layer)` supplies one scheduled closure
  pulse, returning 0 outside the interval or without authored eyelid support.
  It does not schedule blinks or fabricate a closed-eye picture.
- `gaze(direction, extent, has_iris_layer)` bounds movement of an authored iris
  layer, returning zero when unsupported. The consumer owns eyelid clipping and
  safe gaze extents; this does not move an eye painted into a flattened texture.

Invalid timing and channel parameters fail stationary/open. Deformation returns
its original point on invalid arguments, so callers must still validate the
original geometry. There is no automatic art-capability detection. A boolean
capability is a declaration by the game adapter, not proof of suitable art.

A portrait implementing the existing driver interface can hold a clock, pause it
in `pause_motion()`, and in `advance_motion(delta)` sample `breath(time / period)`.
It then applies the sample only to its own mesh or layers. For example, for every
rest vertex:

```gdscript
const Motion = preload("res://addons/story_foundation/presentation/portrait_idle_motion.gd")
# Game-owned arrays: rest_points, breath_offsets, weights, pins; game-owned pivot.
var inhale = Motion.breath(motion_time / period)
for i in rest_points.size():
    vertices[i] = Motion.deform_point(rest_points[i], inhale, breath_offsets[i],
        elbow_pivot, gesture_angle, weights[i], pins[i])
```

The sample is deliberately not a full mesh renderer. A GPU adapter may implement
these same equations, but this CPU helper does not establish GPU equivalence or
performance. It never moves a Node2D root. Game-owned masks must taper through
connected sleeve/shoulder regions; separate chest-only vertices use gesture
weight zero. Pin the support regions before tuning amplitude. An accepted small
angle does not validate a larger one or another pose.

Standalone motion tests run through `scripts/test_portrait_idle.py` with no art,
plugin or narrative dependency. They check loop closure, exact pinned/outside-mask
regions over 49 samples, unchanged chest-only points when gesture changes, pivot
rotation, bounded channels and missing eye capability fallback. They do not prove
visual naturalness. Actual character acceptance, screenshots and private art stay
in the consuming game. See the [performance review guide](character-portraits.md).

## Optional GPU deformation include

`presentation/portrait_idle_motion.gdshaderinc` offers
`sf_idle_deform_point(rest, inhale, displacement, pivot, angle_radians, weights, pinned)`
for CanvasItem shaders, with the same argument order and local-coordinate contract
as the CPU helper. Unlike the CPU convenience default, the shader requires an
explicit `pinned` argument. It has no uniforms, clock, material or renderer of its
own. Include it with a project-relative `res://` path. Apply it to rest-space
`VERTEX` in a consumer-owned mesh; the consumer supplies per-vertex weights and pins.
Do not move the root or repeatedly feed deformed output back as rest geometry.

Pins return the input point. NaN/infinite arguments return the input point too,
including nonfinite rest points: this is not a geometry sanitizer. As with CPU,
finite inputs large enough to overflow intermediate math are outside the useful
coordinate range. Validate geometry and use ordinary local scene units. GPU float
rounding can differ from CPU math; bit-identical results are not guaranteed.

`python3 scripts/test_portrait_idle.py --gpu` requires an actual display and OpenGL
renderer (on Linux CI, `xvfb-run -a` with Mesa). It relocates only optional helpers
and neutral tests into a fresh project, compiles both shader stages and checks
229 rendered cases against CPU results within 0.0002 local units. This includes
49 cycle samples, masks, pins, clamping and nonfinite channel inputs. It is not a
character art acceptance test or a performance benchmark. Headless dummy rendering
is not a substitute. The CI target is native Godot 4.6.3 Compatibility/OpenGL,
not a Web export: browser/WebGL driver behavior and exported integration remain
consumer acceptance work. No Web validation or GPU speedup is claimed.
