# Optional registered portrait structural export gate

Standalone, opt-in Python 3.11+ tooling. Install the isolated dependency:

```sh
python3 -m venv .build/portrait-preflight-venv
.build/portrait-preflight-venv/bin/python -m pip install -r tools/portrait_preflight/requirements.txt
.build/portrait-preflight-venv/bin/python -m unittest discover -s tools/portrait_preflight -p 'test_*.py' -v
```

Each caller-owned character folder supplies `config.json` with `width`, plus
same-size PNG files: `base`, `half`, `closed`, `eye-clear-plate`, `iris-layer`,
`eye-aperture-mask` (each with `.png`). The iris's Godot `.png.import` metadata
must explicitly set `process/fix_alpha_border=false` and
`process/premult_alpha=false` in `[params]`. No private art is shipped.

Read-only checking returns JSON records, including elapsed milliseconds, errors
and warnings. Any hard error produces process exit 1:

```sh
python3 tools/portrait_preflight/check.py path/to/character-a path/to/character-b
```

To make a consuming export depend on this check, invoke its trusted command via
this wrapper (use the venv Python if Pillow is not otherwise installed):

```sh
python3 tools/portrait_preflight/gate.py path/to/character-a path/to/character-b -- godot --headless --path path/to/game --export-release Web path/to/output/index.html
```

All inputs are checked before export starts. Any failed record blocks the entire
command; no partial export is launched. The wrapper uses an argv list, not shell
interpolation. It inherits the caller's working directory/environment, does not
copy or change source files, and propagates downstream exit codes. Usage errors
return 2, command launch errors return 127, and signal exits map to 128+signal.
Only use trusted export commands; this wrapper is not a sandbox. Validation and
export assume inputs remain unchanged; it is not an atomic snapshot or signature.

## Guarantees and limits

Checks cover unreadable/missing/non-PNG layers, dimension mismatch, fully opaque
or empty base, empty iris/mask, config width mismatch, and unsafe/missing iris
import settings. A corrupt character config does not suppress later batch records.
Pixels touching canvas edges are warnings for human inspection, not assertions
of cropped anatomy. The tool does not modify imports or disable the base image's
border correction.

This does **not** validate the full runtime motion definition, identify feet,
infer full-body framing, split layers, detect every alpha artifact, or judge
animation naturalness. Runtime tests and human review remain separate. Import
parsing checks only the stated keys in the params section, not all Godot syntax.
Do not call a structural pass complete animation acceptance.

Foundation CI runs neutral synthetic regression fixtures, including fail-closed
command behavior. Consumer assets and exports are gated only when that consumer
opts into the wrapper; this does not silently enable it for every game. Timing
records describe measured input only and are not 1000-character benchmarks.
