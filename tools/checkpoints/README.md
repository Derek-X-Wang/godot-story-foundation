# Optional durable source checkpoints

Python 3.11+ and Git; no runtime/addon dependencies. This tool is independent of
Foundation's content approval, regression, art and save modules. It protects work
in a temporary workspace by making a source recovery copy outside that workspace.
A local commit, local ZIP, upload request or local receipt is **not** a verified
backup. The currently implemented durable adapter is the user's private Library.
No credentials are embedded and no upload is attempted by this script.

## Small work loop

1. Start from a restored/verified checkpoint. Review scope and exclusions. Run
   `python3 tools/checkpoints/checkpoint.py begin` before a work batch.
2. Use `run --boundary continue -- COMMAND ...` for bounded work. Defaults stop
   further wrapped work after 30 minutes, 20 changed files or 5 MiB of changed
   file sizes, whichever comes first. One command can exceed a budget before the
   post-check observes it; split large operations and checkpoint immediately.
3. Checkpoint before a phase change, an external approval wait, a handoff, or a
   release, even if the batch is smaller. Review/stage intentional changes and
   create a local Git commit. Do not blanket-stage credentials or unrelated work.
4. `pack --output /outside/source/checkpoint-UNIQUE.zip` creates a compact source
   pack and marks local state pending. It includes tracked and non-ignored
   untracked files, including new authored assets, SHA-256 inventory and executable
   modes. Review `manifest.json` and `excluded`. Ignored authored sources require
   explicit `include_ignored` entries in policy. Packs are immutable and never
   overwritten. The policy is included and fingerprinted too.
5. Upload that pack using an authorized durable Library operation **now**, before
   waiting for a GitHub approval or starting the next batch. Retain the unchanged
   successful create/replace result as an external JSON receipt.
6. Independently materialize the exact stored Library version into a new local
   path using the supported Library workflow, including its identity metadata.
   Then run `seal --downloaded /new/path/checkpoint.zip --receipt /receipt.json
   --restore-to /fresh/absent/directory`. It checks the archive hash, Library
   identity/version, every source hash and an actual fresh-directory restoration.
   Seal succeeds only when current source/commit/policy still match.
7. Run `guard --boundary phase` (or `approval-wait`, `handoff`, `release`). Only
   verified, current checkpoints pass. `run --boundary release -- COMMAND ...`
   wraps a release command but does not itself authorize publishing/deployment.

Use `--root /consumer/repo` before the subcommand. Optional `--policy /policy.json`
lets a consumer keep policy outside an immutable tree. Otherwise the optional
`.checkpoint-policy.json` at its root is used:

```json
{"schema":1,"exclude":["build/*","dist/*"],"include_ignored":["native/source-art","native/assets"],"max_minutes":30,"max_changed_files":20,"max_changed_bytes":5242880}
```

The two authored directories above are a consumer example, not Foundation
requirements. Nonexistent declared inputs fail closed. Secret-like names and
symlinks are rejected; this is not a comprehensive secrets scanner. Review scope
before sharing and use private storage for private games/assets. Git submodules
need an explicit source adapter; they are not silently treated as source files.

## Pending, failed, verified

Pack completion means **pending**. A failed/uncertain upload or restore remains
pending and blocks continuation, phase transitions and release. Report the exact
blocker; preserve current source and retry only the failed authorized step. Do
not say backed up, reopen editing or fall back to a local receipt. Emergency
`pack --allow-dirty` preserves unfinished tracked edits but is not a release-ready
commit. Commit and make a fresh verified checkpoint before release.

State lives under Git's metadata directory, never in an immutable source
inventory. After workspace loss or fresh checkout, absent state blocks the guard:
find the durable pack by its saved Library identity, materialize/restore it,
reconstruct a checkout, then create and verify a fresh checkpoint before work.
Do not copy a local state JSON and call that recovery. Cold restoration itself
needs only Python: `restore --archive PACK --to NEW_DIRECTORY --sha256 EXPECTED`.
The restore command does not require an existing Git checkout.

## Exact scope and limits

A source pack restores its listed source bytes/assets and executable bits. It
excludes Git history and generated caches/dependencies; build-tool availability,
remote branch state, runtime correctness and full-repository history are separate
claims. Run normal project tests after recovery. Files ignored by Git are not
included unless explicitly selected. Keep irreplaceable source under the repo or
add a reviewed adapter; external assets are not magically discovered.

An optional `verify-bundle --bundle FILE --ref REF` actually clones into an empty
directory, checks out the ref and checks connectivity. `git bundle list-heads` or
archive checksums alone are insufficient: a bundle made from a shallow checkout
can retain commit/tree objects yet fail ordinary restoration due to absent parent
objects/boundary metadata. Passing this drill proves only that included history
can be restored, not that all remote history is present.

Guards fail closed **when invoked**. They cannot intercept arbitrary shell/editor
operations or prevent platform rollback, process termination or someone bypassing
the wrapper. Local receipts and xattrs are trusted adapter evidence, not signatures
or an anti-tampering security boundary. The enforceable part is a tested command
that rejects risky boundaries; repository instructions make using it mandatory for
transient-workspace work. No permanent platform guarantee is claimed.

Run neutral tests with `python3 -m unittest discover -s tests/python -p test_checkpoints.py -v`.
