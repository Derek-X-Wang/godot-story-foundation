# Optional pending static portrait import

Use this offline, standard-library CLI to bind an **existing** transparent PNG
to a particular concept and an accepted design, then stage a **pending** private
candidate. It does not generate, edit, approve, integrate, animate, or publish
a portrait, judge visual identity, clear rights, or call a provider.

## Caller boundary: where approval comes from

The caller or project must authenticate the reviewer, decide they are
authorized for the character/design, and write a receipt to an independently
controlled approval directory. Configure the approval and pending directories
in trusted orchestration. Never pass directories, expected character identity
or revisions through from raw applicant arguments, model responses, asset
manifests, or request packets. The tool requires a separate approval directory
and refuses receipt symlinks, but directory separation and locally recomputed hashes do **not**
authenticate anyone. Foundation has no identity service, receipt issuer,
signature verification, or access-control bootstrap. If inputs or the command
are run by an operator who also controls the receipt store, that operator
already holds the approval authority; do not expose this CLI to untrusted
submitters with arbitrary flags. Preserve filesystem access restrictions. Keep
directory paths stable and all input and approval contents immutable until the
command completes. The final reread detects stale inputs before publication but is
not a transaction with approval revocation; coordinate revocation or locking
outside the CLI.

The existing [design checker](character-design.md) must report the exact
design record as `accepted`. The directory must also hold one receipt named
`<design_record_sha256>.json`, with these exact fields:

| Key | Value |
| --- | --- |
| `schema_version` | Integer `1` |
| `kind` | `"trusted_design_approval"` |
| `decision` | `"accepted"` |
| `intent` | `"import_existing_static_portrait"` |
| `character_id`, `revision` | Accepted design identity and revision |
| `design_record_sha256` | SHA-256 of the exact accepted design record bytes |
| `review_basis_sha256` | Basis digest from the accepted design review |
| `reviewer` | Exact reviewer label from the accepted record, for correspondence only |

A locally edited accepted label, a hash, or a receipt placed among source
files is not enough. Changing the review, any record revision, or a referenced
file requires revalidation or fresh review as applicable. The receipt authorizes
only the exact design for the stated import-existing intent, not a particular PNG
or request. The request binds the PNG bytes to that design separately, and the
candidate still needs review. A matching receipt does not certify that the
portrait matches the design, or authorize generator calls, final art approval,
export, canon adoption or release.

## Example usage

Supply known identity and revisions from the project, not from a submitted
request. Both input records use the existing design schema: stages `concept`
and `design`; the latter must reference the exact selected concept record as
`upstream_record` and its exact output as `concept_image`. Concept review
state is preserved; this handoff's declared acceptance requirement applies to
the design. Keep references beneath their record directories per that contract.

```sh
args=(
  --concept private/source/concept.json
  --design private/source/design.json
  --portrait private/source/character.png
  --character-id sample_marker
  --concept-revision c-1
  --design-revision d-1
)
python3 -m tools.art.portraits.static_import export-request "${args[@]}" \
  --output private/requests/request.json
python3 -m tools.art.portraits.static_import import-existing "${args[@]}" \
  --request private/requests/request.json \
  --trusted-approval-directory /caller-controlled/approvals \
  --pending-directory private/pending
```

Export creates a new deterministic request with exact artwork, record, revision,
and review-basis bindings; it may export pending records for inspection and
never issues an approval. Import requires the exact canonical request bytes
and revalidates the current source, lineage and receipt before publishing.
The portrait must be a bounded, decodable, nonanimated [PNG](../tools/art/png.py)
with both transparent and visible pixels. Input PNG bytes are not changed.

The successful import creates one new `*.pending.zip`, containing
`portrait.png`, `request.json` and `candidate.json`. The caller must keep
all authoring and pending output outside runtime, export, and public roots.
The CLI rejects directories with a `project.godot` in the directory itself
or its ancestors; it cannot detect other runtime, export, or public trees.
The caller creates and controls these directories and their permissions.
Output publication
uses an exclusive hard link to the complete staged file on the same filesystem:
an existing destination fails instead of being replaced, and filesystems without
hard-link support fail closed. Do not feed this archive to a game build. Final
review and integration remain distinct workflows in the consuming project.
