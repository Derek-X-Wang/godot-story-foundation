# Contributing

Read the [contributor guardrails](AGENTS.md) and
[design decisions](docs/architecture.md#design-decisions) before changing boundaries.
Run the commands in the README before proposing a behavioral change. For
documentation-only changes, check relative links, source claims and
`git diff --check`. Add regression tests for runtime, save, or validation changes.
Keep gameplay-specific policy in content or the consuming game; the addon must
remain reusable.

Do not commit credentials, personal story material, build caches, downloaded
executables, or model transcripts. Use fictional neutral fixtures. Contributions
to first-party code are under the repository MIT license; preserve upstream
licenses and notices for third-party code.

Approval records are audit evidence, not authentication signatures. Never change a
real review to make tests pass: use a separately labeled synthetic fixture. A
candidate or input change must invalidate its existing approval. Keep runtime API,
save schema, content schema, and tool versions separate. An incompatible change
needs migration guidance and replay/save regression coverage.
