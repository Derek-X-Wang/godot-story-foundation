# Local audio technical report v1

`audio_audit.py` measures local decoded audio, without changing inputs. It uses
Python 3.11+ standard library and existing `ffmpeg` / `ffprobe`, no model, extra
Python package, paid service, credential, or network API. FFmpeg input protocols
are restricted to `file,pipe`. The first audio stream is inspected; multiple
audio streams raise a warning. Both PCM and compressed formats are decoded.

## Run

From the repository root:

```sh
python3 tools/audio_audit/test_audio_audit.py
python3 tools/audio_audit/audio_audit.py --loop \
  authoring/audio/ambience.wav \
  --output .build/audio-audit.json
```

For multiple roles and stable UI asset IDs, use a local JSON manifest:

```json
{
  "policy": {"max_sample_peak_dbfs": -1.0},
  "assets": [
    {"id": "room-source", "path": "authoring/audio/source.wav", "category": "source_recording", "loop": false},
    {"id": "room-ambience", "path": "authoring/audio/ambience.wav", "category": "ambience", "loop": true}
  ]
}
```

```sh
python3 tools/audio_audit/audio_audit.py --manifest .build/audio-audit-input.json \
  --base-dir . --output .build/audio-audit.json
```

All asset paths resolve relative to `--base-dir` (default: current working
directory), **not the manifest directory**. Output cannot overwrite an input
asset, manifest, or policy file. IDs must be unique. `--policy policy.json`
overrides manifest policy; each asset's optional `policy` overrides both. Every
effective threshold is repeated in the report. Unknown/invalid policy keys fail
closed. A separate listening derivative must be a separate manifest entry,
with its own ID and hash; the original report does not cover changed bytes.

Exit 0 means measurements completed without technical errors (warnings may
remain); exit 1 means an asset failed or `--fail-on-warning` found a warning;
exit 2 means invalid configuration or a missing tool. Decode errors are reported
per asset so the rest of a batch can finish. Decoding is time/size bounded; a
truncated/limited result must not receive a partial pass.

## Report contract

See `audio_audit.schema.json`. The schema ID is `audio-technical-report.v1`.
Top-level `assets[]` includes `id`, `path`, source hash, effective `policy`,
`decode`, `format`, `metrics`, `loop_risk`, `findings`, and `technical_status`.
The report also records tool versions, UTC timestamp, scope limits, and counts.

- `format`: codec/container/sample format, channels, sample rate, declared
  duration. `metrics.decoded_frames` / `decoded_duration_s` describe actual PCM.
- `metrics.sample_peak_linear` / `sample_peak_dbfs`, `rms_linear` / `rms_dbfs`,
  `max_abs_dc_offset`, `near_full_scale_samples`, `over_full_scale_samples` are
  aggregate metrics; `metrics.channels[]` retains each channel's signed DC and
  other measurements. Aggregate RMS is channel mean-square, **not a downmix**.
- `metrics.silence_intervals[]`: `start_s`, `end_s`, `duration_s`, and
  `kind` (`leading`, `trailing`, `internal`, `full_file`). Each silent sample
  frame must be below the configured amplitude threshold on **all** channels.
- `loop_risk.channels[]`: whole-file `boundary_jump_linear/dbfs`,
  `local_delta_rms`, `ratio_to_local_delta_rms`, and `risk_flagged`. A boundary
  warns only when both amplitude and relative-step limits are exceeded. A null
  ratio with nonzero jump means flat local context; it exceeds the ratio gate.
- `findings[]`: stable `code`, `severity` (`warning` or `error`), `message`.
  Zero-amplitude dB values are JSON `null` (-infinity), never fake 0 dBFS.

`technical_status: pass` means **no configured technical alert**, not a good
sound. `warn` means review the reported risk against the intended asset.
`fail` covers decode/measurement failures and decoded samples over full scale.
`perception_verified` is always `false`; `listening_status` is always
`not_assessed`, at both report and asset levels. The UI must keep these separate
from actual user feedback. No score about realism, appropriateness, quality,
or taste is generated.

## Explicit starting policy, not an industry standard

The defaults are review heuristics: peak above -1 dBFS, absolute DC above .01,
near-full-scale samples at/above 32767/32768; silence at/below -60 dBFS for at
least .1 s, with leading/trailing/internal allowances of .1/.25/.25 s; loop
step above -35 dBFS **and** more than 8 times the local first-difference RMS,
using .02 s at each end. The .1-s silence detection floor still applies even
if an allowance is set to zero, including the `full_file` case: an all-zero
10 ms file is not a .1 s silence event. Set overrides for intentional silence, very
quiet layers, transient SFX, or known material. Defaults are not user approval.
Analysis caps are 256 MiB decoded float PCM and 120 seconds per subprocess.
Configured timeouts must not exceed 86,400 seconds (a subprocess resource bound,
not an audio standard). Exponentiated dB thresholds must produce finite nonzero
linear values. Loop context is clamped to the actual file duration before any
sample-count conversion, preventing overflow on extreme finite configurations.

## Limits

There is no universal LUFS target, and short SFX are **not** rejected for a
music loudness target. v1 reports `integrated_lufs` and `true_peak_dbfs` as null
with `loudness_status: not_measured`: sample peak is **not** true peak. Add an
explicit separate oversampling measurement before making a true-peak claim.
This tool does not prove absence of clipping (near-full-scale counts can both
mislead and miss pre-existing distortion), clicks, unwanted events, or fatigue.
Loop analysis does not assess musical continuity, runtime loop markers, browser
decode behaviour, or actual rendered crossfades. It only checks whole-file PCM
edges when `loop: true`. A loop `no_risk_flagged` is not "seamless".

Runtime gain, buses, mixed playback, browser gesture unlock, timing, devices,
and human hearing remain separate tests. Captured final-mix or 25%-gain review
files can be measured as new assets, but this still does not prove they were
heard. File hashes identify bytes, not rights or the identity of a recorded
event. Source/license review and permission stay outside this tool.

## Composition, source rights and evidence ownership

This optional **offline measurement** stage complements the separate
[Godot audio runtime controls](../../docs/audio.md); it does not replace buses,
settings, envelopes or consumer-owned playback lifecycle. It has no Godot,
narrative, preview-site or other Foundation module dependency. Copy this directory
and run its script directly. Supply existing `ffmpeg` and `ffprobe` executables
(or explicit `--ffmpeg` / `--ffprobe` paths); nothing is downloaded or installed.
Those external tools retain their own licenses/build configuration. The tests
create original mathematical PCM fixtures in temporary directories, plus a FLAC
encoded from a fixture; no recording or third-party audio is bundled.

Keep the stages distinct:

1. The consumer records the original source, creator, license/permission evidence,
   permitted edits/distribution, and intended role in its existing asset inventory.
   File hashes and a passing report do not establish ownership or license clearance.
2. Measure the exact selected source/derivative, keeping its existing stable ID.
   Retain the report alongside source/build inputs in the existing private durable
   checkpoint workflow. A normalized, resampled, edited or final-mix file is a new
   set of bytes and needs its own hash/report; source approval does not transfer
   automatically. This tool never normalizes, repairs or edits an asset.
3. Link technical findings to an exact-version listening/review surface using the
   existing consumer review channel. Keep `perception_verified: false` and
   `listening_status: not_assessed` on this report even after a person listens;
   store that separate review with its own identity and scope. Do not rewrite
   automated evidence into a listening approval.
4. Test actual playback, chosen loop region, gain/mute, interruption and browser
   behavior in the consuming game. Final artistic or user acceptance is separate.

The JSON schema is a structural report description, not a license verifier,
perceptual validator or new mandatory pipeline gate. Tests assert required fields
and important semantics; the CLI does not run a JSON Schema engine. No universal
LUFS/true-peak target or numerical quality score is implied.

Inputs are trusted local files and configuration, not hostile uploads. Absolute
paths and local references are intentionally allowed; `file,pipe` limits decoder
protocols but is **not** a filesystem sandbox or a guarantee against a vulnerable
external decoder. Apply your own isolated execution policy for untrusted files.
Reports can contain caller paths, IDs, tool versions and decoder error text.
Keep private reports/source/license evidence out of the public Foundation repo and
review them before sharing or hosting. Do not copy raw private report files into a
public preview site. The preview generator does not ingest this report automatically.

## Verification and optional dependency limits

```sh
python3 tools/audio_audit/test_audio_audit.py
```

The suite exercises known per-channel peaks/RMS/DC, silence, loop heuristics,
source preservation, corrupt/truncated inputs, FLAC decoding, short SFX without a
LUFS gate, resource caps, effective policy, output aliases and invalid thresholds.
Pure measurement tests need only Python. Decode/CLI fixture tests explicitly skip
if either external tool is missing; a skipped test is not decoded-audio evidence.
The existing read-only CI job explicitly installs Ubuntu's `ffmpeg` package
(which supplies both executables), records their versions, requires both commands,
and runs this suite. The distribution package is not byte-pinned: retain the
reported versions when comparing decoder-dependent results. A missing tool or
failed installation is a CI failure, not a silent full pass. This ephemeral runner
setup does not install anything on a user computer or in the runtime package.
No new CI token permissions, secrets, service or model calls are added. Hosted
execution results must still be checked for the exact candidate commit.
