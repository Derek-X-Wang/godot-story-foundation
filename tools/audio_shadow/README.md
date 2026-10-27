# Optional local audio semantic shadow ranking

This is an **optional, non-gating** inference adapter, not a quality score, listening
approval, rejection threshold, hosted service or full audio production platform.
It complements [technical PCM reports](../audio_audit/README.md), not replaces them.
Neither that tool nor the game runtime imports Torch or this runner.

The small standard-library contract validates a caller-frozen lock and ranks cosine
similarities. The separate explicit runner loads caller-provided local CLAP files
and optional installed packages only when invoked. It never downloads, installs,
trains, uploads audio, calls a hosted model or chooses new labels after seeing scores.
No model weights, audio, private scores, prompts/results or credentials are bundled.

## Inputs and invocation

Supply a JSON lock with exactly these fields (see `lock.schema.json` and the
stricter `contract.validate` checks):

- `schema_version`: integer `1`.
- `model`: `id`, `revision` and `files`: an exact filename→SHA-256 map for
  `config.json`, `preprocessor_config.json`, `model.safetensors`, `merges.txt`,
  `vocab.json`, `tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`.
  These are the supported built-in CLAP/Roberta layout, not arbitrary model code.
  Only optional README/license files may accompany them. No symlink, shard index,
  pickle weights, unknown loadable file or nested model directory is accepted.
- `packages`: exact installed version strings for `torch`, `transformers`, `numpy`,
  `tokenizers`, `safetensors`, `huggingface-hub`. The consumer separately retains its
  complete platform-specific dependency lock and supply-chain evidence; these six
  direct versions are not a transitive wheel lock or dependency authenticity check.
- `labels`: 2–64 unique `{ "id": "...", "text": "..." }` candidates, authored
  before the run. Do not treat omitted possibilities as impossible. The runner
  rejects labels longer than 77 token positions instead of silently truncating.
- `assets`: 1–64 unique entries with `id`, local `path`, `sha256`, `expected_label`
  (a declared label ID or null), and `windows`. Each window contains finite
  `start_seconds` (0–86400) and `duration_seconds` (>0 and ≤10). Maximum 16 windows
  per asset and 256 total. Paths resolve against `--base-dir`, not the lock location.
  Each window must fit the actual decoded clip; no silently shortened crop passes.

```sh
python3 tools/audio_shadow/run.py authoring/semantic-lock.json \
  --model-dir /path/to/already-verified-local-model \
  --base-dir /path/to/consumer --output authoring/shadow-run-001.json
```

Python 3.11+, existing FFmpeg and a separately supplied CPU-only Torch/Transformers
installation are required for real inference. A prior bounded consumer experiment
used `laion/clap-htsat-fused` with Torch `2.10.0+cpu`, Transformers `4.57.6`, NumPy
`2.3.5`, tokenizers `0.22.2`, safetensors `0.7.0`, huggingface-hub `0.36.0` on Linux
x86_64 / Python 3.12. That is an exercised API combination, not a download or
installation instruction, universal support promise or approved model license.
The consumer owns model/weight/dependency/source licenses and installation approval.
No change to those packages is attempted on mismatch.

A private experiment supplied the small loader/preprocessing/ranking method. Its
real-model results and review remain separate consumer evidence; they are not
copied into this public repository. This extracted adapter has **synthetic contract
and boundary tests**, not a new independent real-model accuracy validation. A future
actual run produces separately labeled `local_clap_inference` evidence. Model
output may still be wrong, and a small exploratory contrast does not establish an
automatic acceptance/rejection threshold or user preference predictor.

## Fixed method and report

The runner uses built-in `ClapModel`, `ClapFeatureExtractor`, `RobertaTokenizerFast`,
`local_files_only=True`, safetensors and `trust_remote_code=False`. CPU/eval/inference
mode, batch 1, two CPU threads and seed 0 are fixed; the seed is reset per window.
It decodes the first audio stream to 48 kHz mono float32 with PCM scale conversion,
without loudness normalization. Short windows use the locked model preprocessor's
repeatpad/fusion behavior: they are not extra independent audio observations.

Text features are calculated once; each audio window is compared with L2-normalized
text/audio vectors using cosine similarity, **not softmax, probability, calibrated
confidence or a quality score**. Ties retain frozen label order. If an expected label
is outside the tied top set, the row emits only `expected_label_not_top`; it never
rejects the asset. Small margins and missing candidates need contextual review.
Overlapping windows remain separate rows and are not counted as independent samples
or averaged into a hidden automatic decision.

The completed report contains model file hashes, direct package versions, labels,
asset hashes/windows (without source paths), per-window ranks/scores/margins, fixed
method and canonical lock hash. Decoder version/executable hash are recorded for
real inference. Canonical lock hash includes path strings: relocating input paths
changes that run identity without implying audio bytes changed. Original lock,
source hashes and reports belong in the consumer's existing durable checkpoint
workflow, not a new asset canon. Fixed seeds do not promise cross-version/CPU/FFmpeg
bit-identical results.

All reports force `mode: shadow`, `gating: false`, `quality_approval: false`,
`perception_verified: false`, `listening_status: not_assessed`. `evidence_kind`
distinguishes `synthetic_embedding_fixture` from `local_clap_inference`; never relabel
a fixture as model execution. These fields describe evidence scope, not cryptographic
authenticity: a person who can edit JSON can forge a report.

Output must be a new path. Invalid locks, missing/changed hashes, wrong packages,
nonfinite/zero/mismatched embeddings, short crops, decoder errors/caps and model
failures stop without a completed report. Exit 0 means completed auxiliary ranking,
not an audio pass; exit 2 means failure. No partial ranking is promoted as completed.
Input bytes are checked before/after execution. Concurrent hostile file replacement
is outside the trusted-local-file contract.

## Offline, resources and privacy boundaries

Offline/no-telemetry/no-implicit-token environment flags are set before HF imports;
a Python audit hook rejects socket connection/name-resolution attempts. The runner
never invokes network clients, downloader or installer functions. This is not an
OS-level network sandbox: native libraries/external binaries are trusted, and the
consumer should provide an isolated executor/network policy when required.

FFmpeg uses `file,pipe` only, a 120-second per-decode timeout, and a 256 MiB decoded
PCM cap. Files reaching the cap fail rather than produce partial success. Local
references are allowed: decoder protocols are not filesystem confinement. Model
inference RAM and total time are **not hard-capped by this adapter**; supply an
external process/resource budget appropriate for the already-authorized model.
There is no hidden model installation, persistent cache management or UI service.

Keep model licensing and source/derivative permissions separate from hashes and
scores. Reports omit source paths but contain caller labels/IDs/hashes and can still
be private. Preserve private source, model locks, raw evidence and review records
outside public Foundation and exported games. Do not include arbitrary report files
in a public website. The existing preview generator does not consume shadow reports
or make decisions. Technical checks, semantic suggestions, actual playback/listening
and final user/artistic acceptance remain distinct.

## Tests (no model installation)

```sh
python3 tools/audio_shadow/test_shadow.py
```

CI runs only hand-authored synthetic vectors and temporary placeholder files. It
covers ranks, ties, scale invariance, invalid numbers, exact identity/window locks,
missing/mismatched model files, fail-closed output, mocked decoder failures and
`python -S` import/help with no model packages. These checks do **not** load a real
model, hear audio, test CLAP accuracy or verify successful model inference. The
schema files describe structure; no extra JSON Schema dependency is required.
