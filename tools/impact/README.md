# Optional impact selector (contract v1)

This standalone Python 3.10+ standard-library tool makes a **test plan** for an
exact Git change. It does not run commands, change files, access the network,
reuse test evidence, or declare tests passing. It can be copied independently;
it imports no Foundation runtime, regression runner, game, engine, or browser
module. Git must already be installed. Examples and tests are neutral fixtures.

The consuming project owns its component boundaries, dependency correctness,
scalar-policy bounds, commands, test adequacy, execution, and result validation.
The manifest is trusted, reviewed configuration, not dependency discovery or a
security sandbox. Incorrectly narrow mappings can omit needed tests. Review
manifest changes like executable test configuration, and use `--full` whenever
the declared boundaries do not establish the desired coverage.

## Use

```sh
python3 -m unittest discover -s tools/impact/tests -v
python3 tools/impact/selector.py --root /path/to/consumer \
  --base REVIEWED_COMMIT --head HEAD --manifest /path/to/consumer/impact.json
python3 tools/impact/selector.py --root /path/to/consumer \
  --base REVIEWED_COMMIT --head HEAD --manifest /path/to/consumer/impact.json --full
```

The CLI prints JSON to stdout; exit `0` means the plan was produced, **not that
tests passed**. Exit `2` means invalid configuration, unsafe/unavailable source,
or another read error. Redirect the plan outside the repository or into an
already ignored output directory so the output itself does not dirty the source.
No command in the plan is executed by this tool. A consumer executor must enforce
prerequisite success, validate process/results, and give blocked/unrun suites no
passing credit. Missing commands are explicitly `blocked` in the plan.

```python
from tools.impact.selector import ContractError, load_manifest, select

manifest = load_manifest("/path/to/consumer/impact.json")
report = select("/path/to/consumer", "reviewed-tag", "HEAD", manifest)
```

Public API:

- `load_manifest(path) -> dict`: strict JSON validation; returns a dict subclass
  retaining exact input-byte provenance. Do not mutate it after loading
- `validate_manifest(value) -> dict`: validates without modifying its argument
- `select(root, base, head, manifest, full=False, evidence=None) -> dict`: read-only
  planning; `base` and `head` are mandatory explicit commit references
- `ContractError`: invalid manifest, unsafe checkout, or unavailable provenance

## Manifest

This is an illustrative consuming-project configuration, not a runnable suite
catalog for Foundation. The named commands must be supplied by that project.

```json
{
  "schema_version": 1,
  "components": [
    {"id": "audio", "paths": ["src/audio.gd", "audio_assets/**"]},
    {"id": "gain", "paths": [], "depends_on": ["audio"]},
    {"id": "tooling", "paths": ["tools/**", "docs/**", "impact.json"]}
  ],
  "suites": [
    {"id": "integrity", "components": [], "always": true,
     "command": ["python3", "tools/check_source.py"]},
    {"id": "prepare", "components": [],
     "command": ["python3", "tools/prepare.py"]},
    {"id": "gain", "components": ["gain"], "depends_on": ["prepare"],
     "command": ["python3", "tools/check_gain.py"]},
    {"id": "audio", "components": ["audio"],
     "command": ["python3", "tools/check_audio.py"]},
    {"id": "tooling", "components": ["tooling"],
     "command": ["python3", "tools/check_tools.py"]}
  ],
  "content_rules": [
    {"path": "src/audio.gd", "components": ["gain"],
     "constants": {"EFFECT_GAIN_DB": {"min": -80, "max": 12}}}
  ],
  "generated_paths": ["generated/**"],
  "guard_paths": ["security/release_policy.json"]
}
```

- Unknown fields and duplicate JSON keys fail. `schema_version` is integer `1`.
  `components` and `suites` are nonempty arrays with unique safe identifiers:
  1–128 ASCII letters, digits, dots, underscores, or hyphens, starting with an
  alphanumeric character. All references must exist and both dependency graphs
  must be acyclic. Duplicate names, paths, and dependency entries fail
- Component `paths` and suite `components` are required arrays; empty arrays are
  allowed for a narrowly classified component or a prerequisite/always suite.
  Every component must reach a suite directly or through reverse dependants;
  orphan components fail validation rather than silently losing selected scope
- Paths are exact root-relative POSIX paths or directory-prefix patterns ending
  in `/**`. No other globs, regexes, absolute paths, `..`, or backslashes are
  accepted. Prefix `src/**` matches `src` and everything beneath `src/`.
  Overlapping component paths select the union, not the first match
- Component `A.depends_on: [B]` means an edit affecting B also affects A.
  Impact propagates transitively toward dependants, not toward dependencies.
  In the example, a broad audio change also selects gain, but a verified gain-only
  edit does not select the broad audio suite
- Suite `depends_on` means prerequisite suite IDs. Selected suites pull in their
  transitive prerequisites. Output order is prerequisite-first, using manifest
  order to break ties. This is ordering metadata, not execution or success
- Suite `always` defaults to `false`. An always suite is selected even when the
  commit diff is empty. `command` is optional nonempty string argv, retained
  verbatim. The selector does no expansion, shell interpretation, or execution
- `content_rules`, `generated_paths`, and `guard_paths` default to empty arrays.
  Explicit guard/generated paths always force **all** suites. These declarations
  do not exempt a path from normal component mapping

Known tool/test/doc/manifest files may map only to tooling suites. No hidden rule
turns every tooling change into runtime work. A committed, explicitly mapped
manifest edit follows its declared component mapping. The consumer remains
responsible for reviewing that mapping and testing selection-policy changes.

## Bounded numeric-constant rules

A content rule names one exact regular UTF-8 text file, exact constant identifiers,
finite numeric min/max bounds, and a nonempty set of narrow components. It has no
user-supplied regex. Every allowlisted declaration must exist exactly once in
both versions, with both values inside inclusive bounds. Accepted declaration
forms include:

```gdscript
const EFFECT_GAIN_DB = -12.0
const EFFECT_GAIN_DB: float = -12.0
const EFFECT_GAIN_DB := -12.0
```

Plain signed decimal/scientific numeric literals are accepted; expressions,
hex/underscore literals, strings, booleans, infinity, and arbitrary type names
are not. Comments and quoted strings are distinguished from declarations;
declaration-looking text inside a multiline string cannot narrow an edit.

Narrowing is permitted only for a same-path `M` change with unchanged regular-file
mode. After replacing only the named numeric tokens, the **entire old and new
file bytes must match**. No whitespace, comment, routing, expression, function,
symbol, or other change is discarded. A gain change plus a changed comment is
therefore broad. Added, deleted, renamed, mode-changed, non-UTF-8, binary, or
nonqualifying files use their broad path components. Rules do not override
unknown paths or explicit guard/generated fallbacks. This limited lexical check
is not a full language parser or proof that a constant has no wider consumers;
the reviewed component contract must establish that boundary.

## Conservative selection and provenance

Any unmapped changed path, explicit guard/generated path, nonregular changed Git
entry, or unsupported status selects every suite with its reason. Both sides of
renames are classified. Git control files `.gitignore`, `.gitattributes`, and
`.gitmodules` are always guards because they can affect source interpretation.
Full mode selects every suite independently of mappings and retains all diff
provenance. Missing commands still remain blocked.

`root` must be the repository top level. Base/head refs resolve to exact full
commit and tree IDs. The current checkout's HEAD must equal resolved head.
Tracked/staged changes and every nonignored untracked file are rejected. Tracked
bytes, symlink targets, and POSIX executable modes are compared with the head
objects, even when Git's assume-unchanged/stat cache would hide dirt. Symlinked
parent directories are rejected. Checks run before and after planning; callers
must avoid concurrent writers and revalidate before later execution. This tool
does not lock the worktree for a subsequent executor.

A manifest returned by `load_manifest` must be inside the selected repository,
tracked at head, and byte-identical to its committed blob. It records the SHA256
of the original bytes plus canonical JSON SHA256; a mutated loaded mapping or
stale loaded file fails. A plain in-memory dict is also accepted as explicitly
trusted caller configuration and is identified as `canonical_json`, with no
claim that it came from a tracked file.

Reports include base/head commit/tree IDs; exact manifest and canonical hashes;
raw Git diff SHA256; each changed path's status, old/new mode, Git object ID and
SHA256 of full old/new blob content; classification and reasons; direct and
transitive component sets; selected/skipped suites and their manifest identities.
`content_diff_sha256` hashes the canonical JSON change records, including content
hashes and classifications. Absent file sides have null hashes. Gitlinks refer
to commits rather than file blobs, so their content SHA256 is null and their
changes are conservative. This is Git superproject provenance, not a recursive
submodule inventory. Unchanged ignored/untracked build outputs, external
commands, dependencies, and environment versions are not certified by the plan.

Every report says `status: planned`, `passed: false`, `complete: false`.
Selected suites are `required`, or `blocked` if command configuration is absent.
Skipped suites are `not_claimed`: no previous success, equivalence, or coverage is
implied. Supplying any non-`None` evidence argument raises `ContractError` because
evidence reuse is deliberately unsupported. A separate trusted executor can use
the [optional regression runner](../regression/README.md), but must establish
its own fresh result, coverage, and aggregate-completion guarantees.

## Verification limits

The tests create temporary neutral Git repositories and check scalar narrowing,
false classifications, backend/core dependencies, tool/doc isolation, additions,
deletions, renames, modes, symlinks, unknown/generated/guard fallbacks, exact
provenance, dirty and hidden-dirty sources, invalid manifests/cycles/orphan
components, missing commands, full mode, unsupported evidence, and standalone
CLI use. They establish selector behavior only, not engine/game/browser behavior
or a consuming project's dependency-map completeness.
