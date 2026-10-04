# Optional scene primitives (API 1)

Two independent Godot 4.6.3 `RefCounted` scripts provide axis-aligned navigation
and deterministic draw ordering. Copy either script and its `.gd.uid` sidecar,
plus the repository MIT `LICENSE`, into a game. They have **no dependencies** on
each other, the narrative runtime, Dialogue Manager, art tooling, autoloads,
editor plugins, scene trees, assets, manifests, or network services. Loading them
by path needs no global class registration.

This is a small runtime geometry/ordering module, **not** a scene-art pipeline,
scene editor, animation system, physics engine, or universal game framework.
Game-owned adapters supply footprints, anchor conversions, depth ties, scene
policy, defaults and any save-coordinate recovery. No private scene definitions,
content IDs, characters, images or saved-coordinate conventions are included.

## Rectangle navigation

```gdscript
const Navigation = preload("res://addons/story_foundation/scene/rect_navigation.gd")
var navigation = Navigation.new()
var obstacles: Array[Rect2] = [Rect2(40, 30, 20, 40)]
var configured = navigation.configure(
    Rect2(0, 0, 120, 100), Vector2(2, 3), obstacles, Vector2(10, 10))
if configured.ok:
    var next = navigation.move_ground(Vector2(10, 50), Vector2(100, 0))
    var waypoints = navigation.route(next, Vector2(100, 50))
```

`configure(bounds: Rect2, half_extents: Vector2, obstacles: Array[Rect2],
safe_spawn: Vector2) -> Dictionary` returns `{ok: bool, error: String}`. Input
rectangles must have finite coordinates, sizes and ends, with strictly positive
sizes. Half-extents must be finite and nonnegative. The finite spawn must be
within the closed bounds and outside all expanded obstacles. Expanded rectangles
must remain finite. Wrong Godot argument types are rejected by the typed API;
configuration diagnostics cover values within those types.

Validation is atomic: failure preserves the previous geometry, visibility graph
and motion segments. Success takes an independent geometry copy, builds the
visibility graph and clears `last_motion_segments`. There is no configured
constructor or game default. `is_configured()` reports readiness. Private fields
are implementation conventions, not protection against trusted GDScript that
writes them directly.

- `valid_ground(point) -> bool`: finite anchor inside closed bounds and outside
  every closed expanded obstacle. Bounds already represent allowed foot anchors;
  only obstacles expand by the half-extents plus a 0.01-unit contact skin
- `clamp_ground(point) -> Vector2`: clamp to bounds only; does not escape solids
- `move_ground(start, displacement) -> Vector2`: swept collision, exact bounds
  contact and axis sliding. A solid hit stops a tiny skin distance before contact
  to remain outside the closed rectangle. No endpoint teleport/implicit repair.
  Finite deltas whose float32 length overflows use a float64 length fallback;
  if rounding makes a proposed contact invalid, movement stops conservatively
  at the last valid point instead of entering the solid
- `last_motion_segments: Array[Vector2]`: actual contact/slide displacements from
  the latest move attempt, cleared even when the attempt is rejected. Consumers
  should treat this output as read-only. Reconstructing endpoints by summing
  float32 `Vector2` differences can differ from the returned point by a few ulps
- `segment_clear(a, b) -> bool`: both endpoints valid and the segment misses every
  expanded obstacle, including closed contact
- `route(start, end) -> Array[Vector2]`: deterministic visibility-graph shortest
  route, excluding the start and including the end. Empty means invalid endpoint,
  no travel, or disconnected endpoints. It never repairs endpoints and can route
  within any free component, even one disconnected from spawn
- `repair_ground(point) -> Vector2`: explicit recovery to the nearest tested
  candidate in the spawn-reachable component; equal-distance candidates use a
  lexicographic tie-break. Candidates include projections and rectangle boundary
  intersections with skin clearance. Valid but disconnected points are repaired

Before configuration, validity and segment queries return false, routes are empty,
and move/clamp/repair return the input point unchanged. After configuration,
nonfinite clamp/repair inputs return the explicit spawn; invalid move starts or
nonfinite displacements return the unchanged start. An invalid start is therefore
not automatically made safe by attempting to move it.

Geometry is axis-aligned and static between configurations. A game must configure
again after geometry changes. The preserved numerical policy uses `EPS = 0.01`
and `TIME_EPS = 1e-7`; it targets ordinary scene-unit scales, not arbitrary-scale
or exact arithmetic. Obstacle inflation can close a narrow passage. Remaining
positive channels narrower than twice the corner offset receive extra midpoint
visibility/recovery candidates, including obstacle-to-boundary gaps. At enormous
coordinate offsets the skin can round away; movement then stops conservatively.
At enormous displacement magnitudes the time tolerance may merge distinct hits,
so motion may stop earlier than exact-arithmetic physics would.
Visibility-graph construction is quadratic in node pairs with obstacle scans;
routing uses a simple deterministic Dijkstra scan. This is appropriate for small
scene layouts, not a high-volume dynamic navmesh. No frame-rate, cross-platform
bitwise or huge-coordinate robustness guarantee is implied.

## Depth ordering

```gdscript
const Depth = preload("res://addons/story_foundation/scene/depth_order.gd")
var records: Array[Dictionary] = [
    {"id": "actor", "ground_y": 50.0, "tie": 1, "payload": "game-owned"},
    {"id": "prop", "ground_y": 50.0, "tie": 2},
]
var ordered = Depth.sorted_records(records)
if ordered.ok:
    for item in ordered.items:
        pass # The consuming game chooses how to draw the payload.
```

`static sorted_records(records: Array[Dictionary]) -> Dictionary` returns
`{ok: bool, error: String, items: Array[Dictionary]}`. Each record requires finite
numeric `ground_y` and `tie` (`int` or `float`, not bool/string) and a nonempty,
unique String `id`. Missing/malformed values or duplicate IDs reject the complete
queue and return an empty typed `items` array. Empty input succeeds.

Ordering is ascending **exact numeric ground_y, then exact numeric tie, then
lexicographic id**. Mixed int64/float64 comparison handles the precision boundary
above 2^53 without rounding unequal integers into a false tie. Approximate
comparators can violate transitivity and are deliberately absent. A game that
wants depth bands or contact snapping must compute those keys in its adapter.
Ties and identifiers belong to the game; there is no reserved actor/layer order.

The original input is never sorted in place. Returned dictionaries, nested arrays
and dictionaries are deep copies, including arbitrary extra payload fields.
Object/Resource payload references follow Godot's normal `duplicate(true)`
semantics and remain references; this is not arbitrary object cloning or a save
serializer. Records should not contain cyclic containers.

## Consumer drawing and input integration

These primitives own scene-space geometry and ordering, not the game's renderer,
screen transform or art state. When integrating native scene art, use the relevant
checks below in the game-owned adapter; no scene-art pipeline is added here.

- Share one aspect-preserving scale and offset across scenery, actor anchors,
  labels and hit targets; apply its inverse to pointer coordinates. Use the actual
  scene content area's size, including its UI layout, rather than the outer
  window size. Mask unused gutters and reject their input before hit testing or
  movement. Exercise wide and tall layouts through actual input handlers: a
  mathematical round trip alone does not prove clicks reach the displayed target.
- Reconcile new sprite bounds with its pivot, placement and display scale. If
  the game's hit policy follows occupied pixels, test that policy against the
  exported art rather than retaining placeholder rectangles. Visible alpha bounds
  are not automatically the correct navigation footprint or collision geometry.
- Verify the renderer actually consumes authored layers; a loaded manifest can
  still be bypassed by a procedural special case. Replaced props should draw once.
  Exercise relevant present/absent state combinations, including attached visual
  parts and interaction targets; verify draw calls or rendered output rather than
  only the visibility predicate. Leave a valid background behind removed objects.
- Decorative solids need game-owned navigation/depth treatment or placement clear
  of the walking lane plus the actor's footprint. Inspect the real game at its
  intended scale for obstructed clues, labels and accessible interaction points.
- Compare object labels and prose with the actual exported art and placement.
  Claims such as "behind", "covering" or "out of reach" need support in the
  displayed arrangement and relevant state, not just source IDs or an intended
  concept. Check before/after removal as applicable; correct the art or the claim
  when they disagree. Geometry tests cannot establish a clue's narrative meaning.

Use the existing [art review limits](art.md) and
[packed-resource/capture recipe](testing.md#consumer-content-build-and-capture-recipe)
alongside these checks; neither imported assets nor a concept image prove gameplay
integration or visual acceptance.

## Packaging, pins and upgrades

```sh
python3 scripts/package_scene.py
python3 scripts/test_scene.py
```

The scene-only deterministic ZIP contains exactly the two scripts, their UID
sidecars, MIT license and `SCENE-MANIFEST.json`; it never scans/copies other addon
trees or downloaded dependencies. Its sidecar hashes the ZIP, and the manifest
hashes every payload file. Preserve each selected script's UID sidecar to avoid
untracked UID generation during import. `package_release.py` still offers the
existing full runtime/Dialogue Manager bundle, now also containing the optional
scene scripts; scene-only consumers do not need it.

Pin the exact Foundation source commit and selected file/archive SHA-256 in the
consuming game. API 1 is independent of narrative/save/authoring schema versions
and is not a public release tag. Replace only the selected module as a coherent
version, then rerun the game's geometry, depth, interaction and save-recovery
regressions. The module owns no persistent game state; changing spawn/geometry or
anchor conventions is game policy requiring game-level compatibility tests.

## Verification

`test_scene.py` builds the six-file package twice and verifies byte identity,
manifest hashes and the exact allowlist. It runs each script **alone** in a newly
created minimal project, then copies only that script, its UID and its test into
a different fresh project, removes the original, and repeats editor import and
headless execution. No original `.godot` cache or unrelated code can satisfy a
hidden dependency.

Synthetic tests cover alternate translated/non-square layouts, overlapping
solids, contact, large-displacement tunneling prevention, diagonal/corner sliding,
route segments and repeatability, disconnected routing, positive sub-skin channels,
obstacle-to-boundary channels, reachable recovery, extreme finite movement safety,
configuration rollback, nonfinite/invalid inputs, caller-input isolation, payload
preservation, permutations, near-depth exactness, mixed numeric extremes, and
comparator antisymmetry/transitivity. Python tests verify packaging membership,
hashes, deterministic bytes, missing/symlink rejection and resource independence.

No game content is needed to reproduce these checks. No image/asset authoring or
Aseprite invocation is part of this module's verification.
