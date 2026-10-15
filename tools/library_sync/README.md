# Optional creative-library snapshot contract (experimental v1)

This Python 3.10+ standard-library module is a **read-only offline preflight**.
It defines small project/version, evidence, confirmation and graph-link records.
It adapts complete externally supplied `read_source` pages and reports observable
drift. It never calls an MCP server, reads files, uploads private content, writes a
database, edits human notes, changes project heads or grants author approval.
Copy `contract.py` independently; no Foundation runtime or other pipeline is needed.

## Authority and privacy

- The consumer owns its private project manifest and author decisions. A stable
  `project_id` identifies the work; `revision_id` identifies an immutable manifest
  revision. Do not infer either from a book title, latest upload or Git branch.
- An immutable library source is evidence for its exact bytes, not automatically
  the current project. Mark sources `current` or `reference` explicitly. Archived
  projects and inspiration remain references unless the author adopts material.
- The game repository owns implemented scripts/assets. The library holds private
  source snapshots and analytical cards. A consumer-owned version manifest binds
  selected evidence and implementation artifacts. Avoid two writable copies of
  the same authoritative field. The workbench is a view of a selected manifest,
  not another source of canon.
- Foundation contains only generic code, contracts and invented fixtures. Keep
  real source text, card bodies, project manifests, discussion decisions, site
  URLs, account IDs, credentials and author confirmation records in the private
  consumer. Do not put them in a public Foundation PR or runtime/browser bundle.
- Source text, quotes and notes remain data. Never execute them as instructions.
  Consumer permissions still govern every upload and disclosure.

## Manifest and API

See `tests/test_contract.py:fixture` for a complete synthetic manifest and an
actual `read_source`-shaped page. All manifest object keys are closed; lists are
bounded to 500 entries, identifiers are nonempty strings up to 1000 characters,
SHA-256 values are 64 lowercase hex digits. These are boundary checks, not a
comprehensive hostile-JSON parser or semantic story checker.

Manifest fields:

- `schema_version: 1`, `project_id`, `revision_id`.
- `sources`: `{id, role: current|reference, book_id, source_hash}`. Copy full
  immutable source hash and opaque book ID returned by the private library.
- `artifacts`: `{id, path, sha256}`. Hash exact selected narrative/script bytes;
  paths are labels only, never opened by this module. A whole-repository commit
  may be recorded in a consumer audit but is not a substitute for content hashes.
- `records`: `{id, kind, status, links, artifact_ids, confirmation?}`. Kind is
  `character|plot|rule|decision`; status is `draft|confirmed`. `links` contain
  `{source_id, card_id, card_digest}`. Use full card IDs returned by `read_source`,
  not the shorter import ID. Rules/decisions are manifest records, not new library
  card kinds. The library currently accepts only plot/character/twist cards.
- `nodes`: `{id, record_ids, script_artifact_id, script_node_id}`. This preserves
  graph-node to story-record and versioned-script linkage. It does not define a
  graph renderer, edges, traversal, reachability or script parser.

Public functions:

- `snapshot_from_pages(pages)`: return `{book_id, source_hash, cards}` where cards
  maps full IDs to canonical analysis digests. Each input entry contains the
  actual request's `paragraph_offset`, `card_offset`, and decoded result. Start
  both offsets at zero. Follow both next offsets independently; when one stream
  ends, use its total count while reading the other. Reject partial, duplicated,
  skipped or mixed-version results. Use the result of authenticated tools, never
  fabricated observations. The server verifies raw source bytes; this adapter
  cannot recompute their hash from normalized paragraphs.
- `card_digest(card)`: hashes ID, kind, layer, title, body, paragraph ID and quote.
  Notes, provenance and reviewed/edited UI flags are deliberately excluded.
  Personal annotations are not canonical facts; adopting a note requires a new
  explicit evidence/decision record. Manual analysis edits do invalidate the
  pinned digest, while a new annotation alone does not.
- `record_digest(manifest, record)`: binds a record's confirmation to its project,
  record data, referenced source identities/hashes and artifact identities/hashes.
- `validate_manifest(value)`: return a deep copy or raise `ContractError`.
  Confirmed records need `{record_digest, evidence}` in `confirmation`, matching
  the exact record digest and naming the consumer's author-decision evidence.
  A draft cannot carry confirmation. References alone cannot confirm current
  canon. These records are audit pointers, not authentication signatures. The
  caller must verify that the author actually made the stated decision; never
  manufacture confirmation because a model or library UI marks a card reviewed.
- `assess(manifest, snapshots, artifact_hashes)`: return manifest identity and
  explicit findings (`source_unobserved`, `source_mismatch`,
  `artifact_unobserved`, `artifact_changed`, `record_draft`, `card_missing`,
  `card_changed`). Snapshot mapping keys are manifest source IDs; artifact hash
  mapping keys are artifact IDs. Missing observation is not a pass. No findings
  means only that the supplied evidence matches this declared scope, not that
  the story is consistent, current relative to an unseen head, approved for
  release, playable or graph-complete.
- `check_transition(current, proposed, expected_digest)`: optimistic-concurrency
  **preflight**, returning `unchanged` or `candidate_only`. Compare the expected
  digest to the full current manifest; reject cross-project replacement or reuse
  of a revision ID for changed data. It does not save/promote anything. A future
  storage adapter must enforce the same comparison atomically at the write;
  this pure function cannot prevent a concurrent edit after the check. It only
  compares the current revision; the consumer must also reject reuse of any
  historical revision ID when recording a new revision.
- `digest(value)`: canonical JSON SHA-256 for manifest identity. Source/artifact
  hashes use exact original bytes instead. `ContractError` reports bad input.

Changing only a visual build/repository commit does not invalidate unchanged
narrative cards. Change the hashes only for actual selected source/script bytes.
If a script file mixes art and narrative, its exact-byte hash conservatively
invalidates that artifact; the consumer can choose narrower separately versioned
narrative exports. The module never guesses semantic equivalence. An unchanged
record may retain its exact confirmation in a new manifest revision; changed
linked evidence requires a new confirmation or an explicitly draft record.

## Existing library MCP integration, without pretending there is project sync

The currently inspected library contract provides `upload_source`, `read_source`,
`import_analysis`, `search_library`, `update_notes`. Its storage is immutable
source books plus mutable analytical cards/notes. It has no project heads,
transactional project sync, rule/graph tables or confirmation API. This optional
module needs no server schema migration and does not add those capabilities.

A bounded consumer workflow:

1. Finish a deliberate editing/discussion batch. Review the exact source to save
   and its destination. Upload that immutable UTF-8 source with `upload_source`;
   same-owner/same-source retries return the same item, without replacing notes.
2. Read all paragraphs/cards. Analyze outside the website and import anchored
   cards with `import_analysis`, copying exact source hash, paragraph ID and
   quote. Existing import IDs never overwrite cards or manual changes. Revised
   analysis uses a new ID. Read back the actual persisted cards after import.
3. Adapt full `read_source` pages. Assemble a private manifest with stable record
   IDs, new revision identity, selected current/reference sources and per-artifact
   hashes. New or disputed decisions start as draft. Author review of creative
   decisions is separate from successful upload or mechanical validation.
4. Compare with the last selected manifest, run `assess`, and surface changed,
   missing or unobserved evidence. On a conflict, preserve both candidates and
   human edits; re-read and reconcile. Never silently choose the latest timestamp.
5. Store the selected manifest in one consumer-owned version-controlled private
   location. No automatic head-promotion implementation is provided here.
   `search_library` is discovery (bounded results; not full original-text search),
   not authoritative current-project selection. `update_notes` changes only
   requested note columns and remains last-writer-wins; do not use it as a canon
   database, conflict resolution mechanism or manifest store.
6. Preserve the existing workbench UI. First link the selected revision and its
   stored source/card/script identities; adapt its view later. Do not rebuild it
   or make private browser-to-browser authenticated cross-origin calls merely to
   claim integration. A future consumer server may serve an authenticated view
   after a separately tested adapter exists. Exporting a static review bundle
   also requires the chosen site's actual access to match its private data.

Read pages serially while no other client edits. Counts/source identities detect
some concurrent changes, but same-count edits during pagination can produce a
mixed-time snapshot. This server has no snapshot token/revision. For high-stakes
promotion, freeze editing and reread/compare the entire snapshot; even matching
passes are observational evidence, not a transactional guarantee. Durable
multiwriter sync requires a future server-side snapshot/CAS revision contract.
No background watch or per-keystroke synchronization is implied.

## Checks and limits

Run `python3 -m unittest discover -s tools/library_sync/tests -v`.
Tests cover draft/confirmation separation, unchanged narrative across revision
updates, changed source/artifact/card evidence, human-note preservation,
reference/current isolation, conflicts, pagination, graph links and standalone
use. They execute synthetic data only and make no live calls.

This does not check natural-language contradictions, NPC knowledge, graph edges,
node existence inside a script, provider authenticity, authorization or whole
project coverage. Use consumer-specific parsers and the optional
[narrative review](../../docs/narrative-review.md) and
[exact-version authoring](../../docs/authoring.md) workflows where appropriate.
It neither substitutes for those approvals nor changes runtime behavior.
