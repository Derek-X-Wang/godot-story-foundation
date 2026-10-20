# Contributor guardrails

Read [architecture and design decisions](docs/architecture.md) before changing
module boundaries; use [CONTRIBUTING.md](CONTRIBUTING.md) for contribution rules.

- Keep Foundation composable: independently optional modules and pipelines, small
  explicit contracts, declared dependencies, and replaceable adapters
- Keep game-specific mechanics, story, assets, prompts and review records in the
  consuming game. Defaults and templates are optional; do not require a core fork
  or force every game through the sample's workflow
- Separate immutable definitions from mutable state. Preserve the guarantees of
  modules a game selects, including exact-version review approval and explicit
  save serialization/migration; do not imply coverage for unowned custom state
- Keep reusable contracts, validators, tools and neutral examples public. Exclude
  secrets, private content, proprietary or license-restricted assets, large game
  asset payloads, downloaded dependencies and build outputs
- Distinguish implemented behavior from proposals; keep capability and backend
  claims aligned with the README and architecture document
- Verify standalone use, substitutions and game-specific extensions at the
  affected boundaries. Follow the README checks for behavioral changes; for
  documentation-only changes, check relative links, source claims and
  `git diff --check`
- For work in a transient workspace, follow the optional
  [durable checkpoint loop](tools/checkpoints/README.md): verified off-workspace
  source recovery before phase changes, approval waits, handoffs or releases;
  bounded work batches between checkpoints. Pending/failed backups block further
  risky work. A local commit/archive alone is not durable evidence

## Starting or advancing a consuming game

Use the [production starter](tools/production/README.md) by default for new game
work, before copying a demo's layout or producing an asset batch. Its generated
consumer AGENTS.md and stage-aware brief/checker make prior production lessons
part of the next project's startup. Flow-only prototyping does not require art
approval. Before claiming art integration or release readiness, inspect the actual
composition and close the appropriate record/evidence gate, not just state tests.
For an existing game, read its instructions and adopt or deliberately replace
these checks without overwriting local policy. Keep runtime modules independently
optional; a replacement workflow must name the checks it preserves.

For Web releases, declare the primary browser/environment before testing (Chrome
on the cloud computer by default when capable); native-only games choose a native
target. Safari is optional, never an implicit gate. The starter's portable release
smoke guide and named checks cover normal exported entry, settled Control geometry
and an actual JS/engine bridge when used. Required setup/actions must not depend
on assertion execution. Preserve exact artifact and evidence scopes; app-scoped AX
is not global OS focus evidence and visible pixels do not establish attention.
