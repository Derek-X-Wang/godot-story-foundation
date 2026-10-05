# Optional narrative review: general review and isolated reader

Use this small, consumer-owned worksheet when prose, causality or information
presentation needs review. Start with **one general review**; add an isolated
reader for a particular information history when useful. It adds no runtime,
schema, provider dependency or mandatory multi-agent approval gate. Keep filled
packets, prompts and reports in the consuming game, outside its export root;
review data-sharing permissions before sending private material to a provider.

## Freeze the scope and split the inputs

Record the source/content/build revision, packet hashes, scene and entry point,
route history, language, excluded scope, preparer and author-approval status.
Freeze these before review; an edit requires a new identity and affected review.
Mark unapproved intent as provisional rather than treating it as ground truth.
Choose the mode explicitly:

- **Static read:** only the supplied text/captures were read. Authored transcripts
  are not proof that the game displayed them or that a route is playable.
- **Actual play:** record the build, platform, fresh-start/save state, actions and
  captured observations. Claim only the route and interactions actually exercised.

Prepare two separate packets, with different permitted access:

- **Author/general-review packet:** world truth and timing; intentional deception,
  concealment and uncertainty; each NPC's beliefs/knowledge and how acquired;
  player visibility order; intended choices, consequences and explicit contracts.
  Include relevant source excerpts and test evidence. Keep fact, belief and
  inference distinct. Do not derive requirements solely from existing options.
- **Reader packet:** only observations and offered actions available to the player
  on this route, in encounter order, plus the player's chosen actions. For play,
  reveal each observation only after its action. Exclude source, debug state,
  hidden flags, future content, other branches, author explanations, answer keys
  and other reviewers' findings. Neutral excerpt IDs can map privately to source.

Give each incompatible branch/information history a **fresh reader session with
no inherited author or other-route context**. Do not ask a reader who has seen a
secret to pretend to forget it. Restrict files/tools to the reader packet or play
surface; if that cannot be enforced, record the procedural limits and access
self-report. Log accidental exposure, stop strict blind-reading claims for that
session and restart with a fresh reader if needed. Cross-branch comparison is a
separate, explicitly non-blind activity. A clean self-report is not a full access
log audit or an operating-system isolation guarantee.

## Run two small passes

1. **General reviewer:** read the author packet once. Check motivations and
   affected actors' responses, evidence versus accusations, custody/permission
   transitions, each character's knowledge, information order, required options
   and promised follow-through. Preserve intentional ambiguity or deceit; it is
   not automatically a contradiction. Use the existing
   [causal record](narrative-contracts.md#author-owned-action-causality) and
   [information-order questions](narrative-contracts.md#entry-state-information-order)
   rather than inventing another state model.
2. **Isolated reader, when selected:** before seeing explanations, record what
   happened, what is known versus inferred, what remains confusing, and what the
   next offered actions appear to mean. Cite the visible words/action. Do not
   invent author contracts or infer unseen story truth. Freeze this response
   before the author/general reviewer reconciles it against intent.

Set a budget first: one general pass, one reader pass per selected independent
history, at most one focused dispute recheck, plus explicit time/token/cost
ceilings. Stop at the ceiling and report gaps. Do not expand into a standing panel
or count agreement as evidence. Record actual calls, available model/tool
provenance and measured cost/time; mark unavailable values unknown. Session
wall-clock time can include scheduling and is not pure inference time.

## Copyable result card

```text
Scope: revision/build; packet hashes; entry/route; static read or actual play
Provenance: preparer; author-approved/provisional intent; reviewer/session; tools
Isolation: allowed inputs; actual inputs/access evidence; exposures and limits
Budget: planned ceiling; actual calls/time/cost or unknown; unfinished scope

Finding ID and class: confirmed contract defect / suspected issue / aesthetic
Evidence: exact revision + path/excerpt/observation ID + quote + action/state
Contract: exact authored requirement and approval status, or none established
Reason and impact: expected versus observed; inference/uncertainty kept explicit
Smallest proposed repair: preserve intended uncertainty and allowed routes
Author decision: accept / reject with reason / unresolved
Verification: affected replay/prose review/tests; evidence or not yet run
```

A confirmed defect needs a supported violation of an explicit, author-approved
contract. Without that basis, retain a suspected issue for author judgment;
readability confusion is useful even when no logic defect is established.
Aesthetic preferences stay separate. A reader cannot confirm a hidden promise
that was never in their input. Deduplicate by evidence and violated requirement,
not by how many reviewers voted. For a specific dispute, provide only the needed
source/contract to one focused recheck; record unresolved differences for the
author rather than repeatedly sampling until consensus appears.

## Close the loop without overstating it

The author decides creative intent and repairs. Keep hypotheses and rejected
findings in the private audit, including packet/version changes and information
flow risks. After a repair, replay the affected real route and run applicable
[causal-action](testing.md#consumer-causal-action-contracts) and
[interrupted-UI](testing.md#consumer-interrupted-ui-contracts) checks; update the
exact-version [authoring approval](authoring.md#a-real-review-cycle) if using that
optional pipeline. This worksheet never creates or substitutes for its approval.
Human judgment and deterministic tests remain necessary. A review pass, an
AI-authored provisional label, or success on a few synthetic cases establishes
neither production accuracy nor narrative quality. Static reading does not claim
runtime, rendering, browser, audio, or human playtest coverage.
