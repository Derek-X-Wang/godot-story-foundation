# Optional production handoff: flow prototype to art-integrated game

Use this consumer-owned worksheet when a validated story/flow prototype becomes
an art-integrated playable scene. It connects the existing
[authoring review](authoring.md), [art design reviews](art.md) and
[scene integration checks](scene.md#consumer-drawing-and-input-integration).
It adds no generator, runtime API, approval command or mandatory presentation
template. Keep filled briefs, game assets, captures and decisions in the consuming
game's appropriate authoring storage, outside its export root.

**A flow prototype is a semantic reference, not automatically an art reference.**
Story/flow acceptance, composition acceptance, asset acceptance and release
verification are different decisions. This worksheet describes review practice;
it does not claim that a particular game or fullscreen implementation has passed.

## 1. Label the references before production

Record the exact version, intended use and acceptance status of each input:

- **Story/flow reference:** narrative order, available actions, branch outcomes,
  costs, custody, knowledge sources, commit/cancel boundaries and return behavior.
  Preserve approved semantics while replacing their presentation.
- **Art reference:** explicitly selected style, palette, character identity,
  materials and visual treatment. A prototype screenshot, debug diagram or
  placeholder only defines these if the owner explicitly accepts it for that use.
- **Composition/staging reference:** camera/framing, human scale, actor and prop
  placement, depth, movement, interaction targets, dialogue and choice overlays.
  Mark proposed relationships separately from accepted ones.

One artifact may serve several roles, but record each role explicitly. Do not
inherit a prototype's split panes, placeholder geometry, screen proportions or
image-above-text layout simply because its flow passed. Conversely, art approval
does not authorize rewriting dialogue, timing, action consequences or who knows
what. Reconcile any intentional semantic change through the game's existing
authoring/contract review rather than calling it a cosmetic change.

## 2. Establish a scene composition before asset expansion

Write a short art-integration brief: scope and entry/exit states, accepted
references, provisional decisions, target viewports, intended camera and UI
relationship, essential visible actions and missing assets. Reuse
[structure-before-detail review](art.md#scene-design-structure-before-detail)
instead of drawing detail around an inherited debug layout.

When the approved direction is a fullscreen, scene-led game:

- Make the environment the primary game view, with dialogue and choices composed
  over that scene. Do not put a room image into a scrolling text card and call it
  scene integration. Fullscreen here describes the composition within the game
  viewport; it does not require operating-system fullscreen mode.
- Stage people and props in the same readable space. Check character scale,
  contact/occlusion, movement paths and the visual relationship to action targets.
  A loaded background alone does not demonstrate inhabitable staging.
- Keep the action the player is choosing or observing visible when the overlay is
  open. Review long text and many choices as well as the shortest dialogue.
  Adapt framing and overlays for the selected wide/narrow viewports without
  silently cropping out essential actors or cues.
- If approach, retreat or another movement is part of the approved interaction,
  show its progress and cancellation coherently. Actor movement, camera movement
  and other staging choices are game-owned alternatives, not Foundation mandates.

This is a conditional composition checklist, not a ban on visual novels, panels
or another deliberately selected format. Do not prescribe universal resolutions,
overlay percentages, camera paths, character poses or pixel dimensions.

## 3. Review a small composed playable slice first

Build one representative scene slice with its real environment, intended actors
or explicitly labeled stand-ins, dialogue/options and relevant movement. Choose
states that stress the composition: entry, a substantial dialogue/choice overlay,
the important action, and its resulting scene. Include cancellation if relevant.

Run import/startup and focused semantic checks while building. Then inspect the
**actual rendered composition** before expanding the asset batch or spending the
full regression budget on the candidate. This ordering catches a wrong visual
direction early; it does not waive tests or postpone safety-critical checks.

Use the game's real renderer and current build, not only an isolated source image,
a concept mockup, headless Label assertion or successful export. Record build and
asset identities, platform, viewport, route/state and captures. A still frame can
support framing review; motion, transitions and input need actual playback or an
appropriate recorded sequence. Follow the
[current-frame capture recipe](testing.md#consumer-content-build-and-capture-recipe).

Have the owner or designated reviewer record one of:

- **Accepted for this scope:** name the composition/asset aspects and states.
- **Provisional:** usable for integration work, with named remaining decisions.
- **Rejected:** identify the mismatch and revise the affected composition first.

Acceptance of a blockout permits the stated next step, not a claim that stand-ins
are finished art. Track each asset as placeholder, candidate or accepted with its
version. Missing character/animation/effect art remains explicit. A temporary
handoff to an older presentation is a bounded integration bridge, not evidence
that the whole scene has been converted or approved.

## 4. Integrate assets without changing interaction meaning

After the composition direction is accepted, extend the art in bounded slices.
Reuse the existing [character pipeline](art.md#quick-start-no-editor-or-game-runtime-needed)
where appropriate and the [drawing/input integration checks](scene.md#consumer-drawing-and-input-integration).
Scene-art generation itself remains unimplemented in Foundation.

- Route choices through the original owning command/interaction boundary.
  Preserve preconditions, costs and exact commit/cancel behavior. Do not replace a
  cancellable approach with an immediate state-changing choice just to drive art.
- Keep read-only inspection, replay and decorative presentation read-only.
  Reopening, resizing, skipping or closing a visual sequence must not recommit an
  action or silently reveal information.
- Where knowledge depends on seeing a cue, verify that the current composed view
  actually presents that cue under the game's stated position/focus/timing rules.
  Asset loading, hidden controls, an offscreen sampler or an elapsed animation
  alone is not visual evidence. Keep readability/acknowledgment policy explicit;
  pixels on screen do not prove that a person understood them.
- Preserve approved facts and information order across new art and old/new
  presentation boundaries. If needed art or staging is missing, keep the relevant
  feature explicitly incomplete rather than inventing an observation or silently
  awarding knowledge.

Use the existing [causal-action](testing.md#consumer-causal-action-contracts) and
[interrupted-UI](testing.md#consumer-interrupted-ui-contracts) recipes for state,
replay, stale callback and modal checks. Do not create a second authority for
story state inside an art adapter.

## 5. Close each gate with the evidence it actually needs

1. **Flow baseline:** identify accepted narrative/actions/knowledge contracts and
   their tested scope. A visually crude prototype can pass this gate.
2. **Art direction and composition:** accept the intended references and a real
   composed slice at target game scale. Passing flow tests cannot pass this gate.
3. **Asset integration:** confirm selected asset versions, visible people/actions,
   overlay readability and the real interaction boundaries. An isolated approved
   image or a placeholder composition cannot pass final asset acceptance.
4. **Release verification:** run the affected regression and packaging/platform
   checks against the final candidate, and recheck its rendered composition.
   Report failed, blocked and unrun lanes. A screenshot cannot pass state tests;
   state-test success cannot pass visual acceptance.

A changed reference, crop, asset, camera, UI or interaction can invalidate an
earlier decision in its affected scope. Re-review that scope and rerun applicable
checks; do not silently carry an old approval onto changed bytes. When using the
optional authoring pipeline, semantic content edits also require its existing
[exact-version approval cycle](authoring.md#a-real-review-cycle).
Use the [impact selector](../tools/impact/README.md) only within its declared
contracts; test selection is not evidence that the selected tests passed.

## Copyable handoff and acceptance card

```text
Scope: scene / entry and exit / selected routes / excluded or unfinished work
Identity: source/build revision; asset/reference versions or hashes
Flow reference: accepted semantics; relevant action/knowledge/cancel contracts
Art reference: intended use; accepted/provisional/rejected; decision owner
Composition: camera/scene/UI relationship; target viewports; visible key actions
Assets: accepted / candidate / placeholder; missing work and temporary bridges
Rendered evidence: actual build/platform/viewport/state; captures/playback links
Decision: reviewer; date; accepted aspects and limits; unresolved mismatches
Checks: focused semantics; final regression; packed/platform lanes; exact results
Next gate: required evidence; owner; changes that require renewed review
```

Keep reference acceptance, rendered observations and automated results separate.
Use neutral templates in Foundation; retain private story details, production
art, prompts and actual review records in the consuming game. Follow the existing
[durable checkpoint loop](../tools/checkpoints/README.md) for transient work.
