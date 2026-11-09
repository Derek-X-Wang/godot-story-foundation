# Optional portrait animation design

Category: **Art → Character portraits → Idle and talking**. Use this design and
visual-review guide when authoring animated standing portraits or dialogue busts.
It is not a runtime implementation, portrait asset schema or automated quality
gate. Portrait source/crop/delivery contracts and animation backends remain
unimplemented in Foundation; see [art boundaries and status](art.md#boundaries-and-status).

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
