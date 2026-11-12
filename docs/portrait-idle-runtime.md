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
