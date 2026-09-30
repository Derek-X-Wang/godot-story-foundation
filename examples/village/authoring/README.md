# Synthetic public village fixture

Copyright (c) 2026 Derek Wang. MIT licensed.

This deliberately small, original village scene contains no private story data and needs no model or network access. Mira keeps the village notice board. Seeing the bridge teaches only the player; sharing the news teaches Mira. One guarded choice consumes chalk, grants a map, and awards five coins once.

- `packet.json`: human-owned scene card, persona, minimal world context, registries, authoritative rules, and four simulation fixtures
- `request.json`: provider-neutral export of that packet and the response contract
- `response.json`: original hand-written offline response, not model output
- `candidate.json`: imported response, explicitly unapproved
- `review.json` / `review.txt`: machine validation, branch coverage, and full textual diff; not an approval
- `approval.fixture.json`: **synthetic test approval, not a human review**

The synthetic approval is accepted only with `build --allow-test-fixture`. There is no CLI command to turn a response into an automatic human approval. For real content, read the review and use `approve --reviewer YOUR_NAME --yes-i-reviewed` explicitly. Regenerating, reformatting, or changing a packet/candidate/review invalidates any approval tied to its exact previous bytes.

Do not copy this authoring directory into a Godot project. Stage only the compiled `content.json`, `presentation.dialogue`, and optional `build-manifest.json`; leave packet, request, candidate, review, approval, and audit files outside the game root.
