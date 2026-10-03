# Optional native audio primitives

**API 1, Godot 4.6.3, native GDScript.** Three small `RefCounted` scripts use only
Godot built-ins. Each works alone, at any resource path, without the narrative,
scene, art, replay or authoring modules, Dialogue Manager, a global class name,
autoload, plugin, audio asset or UID sidecar. Select one script or use all three.

This is a runtime-controls toolkit, not a music asset pipeline. The consuming game
owns bus selection, defaults, settings UI, player/stream lifecycle, cue routing,
transition state, accumulated elapsed time, track trim, assets and licensing.
Foundation does not choose a save location, install a singleton, advance a fade,
start/stop a player or serialize game state. Asset generation, music catalogs,
provenance, import and export pipelines remain separate future work.

## Installation and composition

Copy the chosen `.gd` files from `addons/story_foundation/audio` into a Godot
project and preload them by their installed paths. There are no cross-script
preloads. Editor import may generate local UIDs; these are not prerequisites for
this path-based API. A game can replace any one helper while retaining the others.

```gdscript
const Buses = preload("res://addons/story_foundation/audio/web_safe_audio_buses.gd")
const Preferences = preload("res://addons/story_foundation/audio/audio_bus_settings.gd")
const Envelope = preload("res://addons/story_foundation/audio/gain_envelope.gd")

# Entirely consumer-owned names, defaults and path.
var selected := ["Master", "Primary"]
var levels := {"Master": 1.0, "Primary": 0.75}
var mutes := {"Master": false, "Primary": false}
var path := "user://my-audio-preferences.cfg"

func configure_audio() -> Error:
    for name: String in selected:
        if Buses.ensure_bus(name) < 0:
            return ERR_DOES_NOT_EXIST
    var restored := Preferences.load(path, selected, levels, mutes)
    if restored != OK and restored != ERR_FILE_NOT_FOUND:
        return restored
    return Preferences.apply(selected, levels, mutes)

func sample_transition(start_gain: float, target_gain: float,
        elapsed: float, duration: float) -> float:
    return Envelope.sample(start_gain, target_gain, elapsed, duration)
```

Call bus/server operations on the main thread, without concurrent layout changes.
Use distinct mutable dictionaries for levels and mutes; mutations are explicit.
None of the helpers owns a persistent copy of caller state.

## Bus creation

`static ensure_bus(bus_name: String, send: String = "Master") -> int`

- Existing name: return its current index without altering any bus, including its
  gain, mute, solo, bypass, effects, routing and position. The `send` argument is
  ignored when the requested bus already exists
- New name: require a nonempty name and an already existing send; increase
  `AudioServer.bus_count` by one, then name and route the appended bus. Previous
  buses retain their indexes and properties. New buses keep normal engine defaults
- Return `-1` for an empty name or absent send, without changing the layout. A new
  bus cannot send to itself. A custom send must be created before its children

The explicit count-increase path avoids the `add_bus(-1)` sample-graph insertion
path exercised by Godot 4.6.3's exported Web driver. This is a narrowly tested
creation strategy, not a blanket promise of browser audio compatibility. Existing
layouts are never repaired or overwritten by this helper.

## Preferences and server application

All functions are static. `buses: Array` is the explicit selected set: unique,
nonempty `String` names, without spaces, tabs, line breaks or square brackets.
These restrictions avoid lossy ConfigFile section names. An empty selection is
valid. Argument types are enforced by GDScript; value-level failures are returned.

- `set_level(bus_name: String, value: float, buses: Array, levels: Dictionary)
  -> bool`: reject unknown names, malformed selections and nonfinite values;
  otherwise clamp to `[0, 1]`, write only that dictionary entry and return `true`
- `set_muted(bus_name: String, value: bool, buses: Array, mutes: Dictionary)
  -> bool`: reject unknown names/malformed selections; otherwise write only that
  boolean entry. The setters do not apply or save anything
- `inaudible(master_bus: String, bus_name: String, levels: Dictionary,
  mutes: Dictionary) -> bool`: true if either named preference is muted or has
  finite numeric gain at/below zero. Missing or invalid entries are neutral
  (unity gain/unmuted). It is a preference query, not an output-device, effect,
  intermediate-send, solo-state or stream audibility measurement
- `apply(buses: Array, levels: Dictionary, mutes: Dictionary) -> Error`: validate
  every selected entry (finite numeric level, boolean mute) and resolve every
  selected existing AudioServer bus before changing anything. Invalid state gives
  `ERR_INVALID_PARAMETER`; an absent server bus gives `ERR_DOES_NOT_EXIST`.
  Successful application clamps each level, sets dB gain to
  `linear_to_db(maxf(level, 0.0001))`, and sets mute to `muted or level == 0.0`.
  Zero therefore means a **−80 dB floor plus hard mute**, while a tiny positive
  value uses the floor without forcing mute. A later positive unmuted preference
  clears that mute. Only selected volumes/mutes change; no bus is created

Integer dictionary levels are accepted; bool, String, NaN and infinity are not.
Application and saving do not rewrite caller dictionaries or extra entries.
The game decides whether to apply/save after each edit or only on confirmation.

## Persistence, old preferences and failures

`static save(path: String, buses: Array, levels: Dictionary, mutes: Dictionary)
-> Error`

`static load(path: String, buses: Array, levels: Dictionary, mutes: Dictionary)
-> Error`

The explicit path must resolve to an absolute file path, including `user://` or
`res://` where writable. Parent directories must already exist; the helpers do
not create them. Keep trusted local preferences outside exported read-only assets.
The caller reserves the sibling `path + ".tmp"` and serializes writes to that
path; concurrent processes/writers and hostile path/symlink inputs are outside
this contract.

The format is an ordinary Godot ConfigFile with one section per selected bus:

```ini
[Primary]
level=0.75
muted=false
```

Save validates the entire selected state, writes clamped finite numeric levels
and boolean mutes to the temporary sibling, then renames it onto the destination.
Invalid state/path returns `ERR_INVALID_PARAMETER` before a write. File-save and
rename errors propagate. A failed rename attempts to remove the temporary file;
the previous destination remains untouched in the tested failure cases. No delete
of the old destination occurs before replacement. Unselected sections, comments
and unrelated keys are not preserved: this is the caller's dedicated settings
file. Empty selections save an empty ConfigFile.

On Web, a successful rename calls `JavaScriptBridge.force_fs_sync()`. `OK` reports
local write/rename success and a sync request, **not** a browser-persistence
acknowledgement. Browser storage availability, quotas, private browsing, crashes,
OS/filesystem durability and simultaneous writers are not guaranteed. Native
same-directory replacement/error behavior is tested; other platform filesystem
semantics and actual browser persistence require consumer verification.

Load reads the complete ConfigFile before touching caller dictionaries. Missing
files return `ERR_FILE_NOT_FOUND`; read/parse errors leave both dictionaries
unchanged. It merges only selected finite numeric levels and real boolean mutes.
Finite levels are clamped; unknown sections and invalid/missing values are skipped.
It does not clear defaults or require a schema marker. An older file missing a
newly added bus or key therefore retains the defaults that the game supplied.
A malformed complete file is not partially merged.

This is backward-compatible default retention, not automatic semantic migration.
If a game renames a bus, changes default policy or needs a different format, it
owns that migration and its tests. The native suite verifies byte compatibility
with an independently authored bus-section ConfigFile, missing-new-bus defaults,
invalid values, read/write/rename failures and unchanged caller/file state.

## Stateless gain envelope

`static sample(from_gain: float, target_gain: float, elapsed: float,
duration: float) -> float`

For positive duration, sample `t = clampf(elapsed / duration, 0, 1)`, smooth it with
`t * t * (3 - 2 * t)` and return Godot `lerpf(from_gain, target_gain, weight)`.
Negative elapsed clamps to the initial sample; completion/overshoot clamps to the
final sample. Nonpositive duration returns the target immediately. Inputs must
be finite; NaN/infinity have no defined module contract. The API preserves native
`lerpf` floating-point behavior, including rounding at endpoints.

Endpoints are intentionally not constrained to `[0, 1]`: the game may interpolate
linear gain or dB. It chooses duration, gain units, pause/interruption policy and
when to stop a completed player. To retarget continuously, capture the current
sample and use it as the new start. No state, timer, player or update loop is
hidden in the helper.

## Packaging, pins and verification

```sh
python3 scripts/package_audio.py
python3 -m unittest discover -s tests/python -p test_audio_packaging.py -v
python3 scripts/test_audio.py
# Optional: pass the exact Godot 4.6.3 exported engine driver to test its graph.
node tests/audio/test_web_bus_driver.cjs /path/to/exact/export/index.js
```

The deterministic ZIP contains exactly three scripts, the first-party MIT license
and `AUDIO-MANIFEST.json`; the manifest hashes every payload, and a sidecar hashes
the ZIP. It copies no other module, UID, asset, project setting, dependency or test.
The existing full addon package also includes these scripts, but is unnecessary
for audio-only use. Pin the exact source commit and chosen file/archive SHA-256 in
the consuming game. API 1 is separate from the narrative/save/content versions.

`test_audio.py` builds the package twice and checks identical bytes, hashes and
membership. For **each script separately**, it creates a minimal project containing
only that script and its synthetic test; imports and runs it; copies just source,
test and project configuration to another location; deletes the original project;
and repeats with no original UID or `.godot` cache. Native cases cover existing
bus preservation, exact append order, finite/default/error settings behavior,
legacy-format persistence, smoothstep trajectories/endpoints and retargeting.
Python tests also check missing/symlinked package inputs and isolation boundaries.

The optional Node test exercises the actual supplied exported driver's sample-bus
graph with synthetic Web Audio nodes. No engine driver is bundled here. It does
not run a browser, hear output, verify a real device, exercise a persistence sync
or establish playback/autoplay permissions. The existing public workflow runs
the native audio runner and Python packaging checks using its installed Godot and
Python. The exported-driver test remains opt-in/local-only. The workflow gains no
new permissions, secrets, dependencies or triggers; a configured step is not an
observed hosted result.
