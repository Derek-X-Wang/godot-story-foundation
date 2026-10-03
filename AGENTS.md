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
