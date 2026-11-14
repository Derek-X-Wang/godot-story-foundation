# Optional portrait animation design

Category: **Art → Character portraits → Idle and talking**. Use this design and
visual-review guide when authoring animated standing portraits or dialogue busts.
This guide is not a portrait asset schema or automated quality gate.
The optional [motion primitives](portrait-idle-runtime.md#optional-motion-primitives)
implement small numerical building blocks, not automatic portrait animation. Portrait source/crop/delivery contracts and animation backends remain
unimplemented in Foundation; see [art boundaries and status](art.md#boundaries-and-status).

## Compose a living portrait, not a moving card

Use two independently optional layers of performance:

1. **Base idle:** chest/torso breathing, blinking and subtle gaze movement where
   the actual art supports them. This gives a listening character a quiet sense
   of life; it is not a requirement to animate every region continuously.
2. **Pose-specific gesture:** add motion that the posture invites. An extended
   forearm may rotate slightly around its elbow while the shoulder participates
   in the breathing. Do not substitute whole-hand translation for an elbow
   gesture, or force the same gesture onto every character and pose.

Keep planted feet and the intended support/contact regions fixed. Root rotation,
whole-card scaling or drifting the entire painting is not a shortcut to body
motion. Keep chest amplitude separate from forearm amplitude so approved breathing
can remain unchanged while a gesture is tuned. Small-angle local mesh deformation
is one option, not independent bones, physical simulation or a universal rig.

Missing eyelid/iris layers are missing capabilities, not an invitation to invent
them at runtime: omit those channels and preserve the original image. A single
flattened portrait may still support reviewed local breathing or pose deformation.
Eyeballs must not slide the painted eyelids or leave their sockets; blink overlays
must not leave duplicate open eyes. Add these channels only after suitable assets
and visual validation exist. Keep game-specific masks, pivots and calibration in
the consuming game.

## Choose the character's performance

Record the intended behavior alongside the character's selected design. For a
direction that emphasizes female characters' figures, use this baseline:

- **Female portraits:** natural eye blinks, talking mouth shapes, and visible but
  restrained chest/upper-torso rise and fall from breathing. The breathing motion
  should express the chosen figure through the body and clothing silhouette,
  rather than add unrelated bounce or distort the accepted anatomy.
- **Male portraits:** natural eye blinks and talking mouth shapes are the baseline;
  the same chest/torso breathing emphasis is not required.

This is a selectable art direction, not a universal rule for every game or body.
Keep owner-approved differences in expression, posture, intensity and motion for
each character. Do not flatten those differences into identical animation, or
silently redesign accepted artwork to make it fit a shared rig.

## Idle and talking are distinct

- **Idle/listening:** use natural blinks and the character's selected breathing
  behavior. The mouth holds the intended resting expression; it should not cycle
  through speech shapes just because an idle loop is running.
- **Talking:** activate mouth movement for that speaker's speech/presentation
  interval, then return to the intended resting expression. Continue or adjust
  blinks and breathing as the approved performance requires. A simple talking
  loop is not a claim of phoneme-accurate lip sync.
- **Breathing:** show local chest/upper-torso expansion and relaxation, with
  clothing responding coherently. Keep the portrait's placement stable. Moving
  the entire unchanged picture up and down is rigid drift, not evidence of
  breathing; uniformly scaling it is not a substitute either.

Timing, amplitude, mouth shapes, affected regions and masks belong to each
character. Reusable control logic does not establish that another face, pose or
outfit is calibrated correctly. No fixed blink rate, breath duration, deformation
formula, layer count, rig or provider is prescribed here.

## Coordinate optional arm motion with breathing

When a portrait includes subtle upper-arm or forearm motion, compose it with the
selected breathing behavior as one performance. Check how the shoulder carries
the arm and how the sleeve, wrist and torso boundaries remain connected. A shared
phase can help coordinate these regions, but it is an implementation choice, not
a requirement that every character use the same cycle or move every region in
lockstep. Keep each character's timing and amplitude in the consuming game.

Use only the control detail the shot needs. A small idle gesture can keep the
hand unchanged and carry it with the forearm; it does not require separate
control for every finger or joint. Where a grasp is actually needed, a separate
thumb and grouped fingers may suffice for that angle. Held props, alternate grips
and large arm gestures are separate work with their own visual review, not a
prerequisite for a simple idle. Do not transfer a small-angle mesh deformation's
acceptance to a larger pose range.

## Define portrait visibility and pause behavior

Before runtime integration, choose how a portrait behaves when it or its parent
panel is hidden, paused, removed or shown again. For a simple idle, suspending
hidden updates and resuming from the held pose is one valid policy. Other games
may deliberately reset or resynchronize; record the choice rather than silently
advancing hidden time and jumping on reappearance.

Verify repeated hide/show and pause/resume transitions, parent visibility and
multiple portrait instances. Explicit hiding does not establish automatic
screen-off culling. The optional [idle-host driver](portrait-idle-runtime.md)
implements explicit visibility, pause and clock ownership for a ready portrait.
This guide does not implement those behaviors itself, and neither the guide nor
the driver establishes integration into a game's dialogue UI.

## Review every character separately

Inspect the actual rendered portrait at its intended crop and display size,
including the composed dialogue UI. Watch enough playback to see the relevant
blinks, a full breathing cycle where selected, and idle/talking transitions.

- [ ] Eyes close and reopen naturally without misplaced lids, edge artifacts or
  loss of the selected expression.
- [ ] The idle mouth rests as intended; speech motion starts and stops with the
  intended speaker/interval, without residual flapping or a stuck open mouth.
- [ ] For a portrait using the breathing emphasis, chest/torso rise and fall is
  visible at normal viewing size, natural for that figure and clothing, and not
  merely whole-image drift, uniform zoom or unrelated chest bounce.
- [ ] Facial features, torso, clothing and crop stay coherent through the motion
  and transitions. Record visible mask seams, clipping or distortion as defects.
- [ ] Where arm motion is selected, breathing, shoulders, arms and clothing read
  as one performance without detached joints, edge tears or unrelated swaying.
  Check a complete loop at the intended display size, not only enlarged stills.
- [ ] In the consuming UI, verify the selected visibility and pause policy across
  repeated transitions; one portrait's state must not unintentionally alter
  another instance. Preserve the accepted appearance when adding lifecycle logic.
- [ ] Repeat these checks for every character and affected pose/outfit revision.
  A working first character does not approve the next; male portraits need not
  pass a chest-motion requirement that was not selected for them.
- [ ] Retain the character/revision, selected behaviors and intentional
  differences, playback evidence, findings and actual review decision in the
  consuming game's records. Mark unobserved behavior as unverified.

Logic/state tests, observed rendered behavior and owner/designated-reviewer
acceptance are separate evidence. Record checks and passing exports cannot prove
natural motion or grant approval. Follow [character-design provenance](character-design.md)
and the existing [production gates](../tools/production/README.md) where selected;
keep character art, calibration, prompts and private review records in the game,
not in Foundation.
