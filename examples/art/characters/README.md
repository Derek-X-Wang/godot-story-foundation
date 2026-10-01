# Synthetic character sprite fixtures (MIT)

`narrow.png` and `broad.png` are tiny original geometric test drawings. They are not
private game characters, reference sheets, copied third-party art, or production
character designs. Their editable source is the literal ASCII drawing arrays in
`create_fixtures.py`; rebuilding regenerates identical PNG and manifest bytes.

```sh
python3 examples/art/characters/create_fixtures.py
python3 -m tools.art validate examples/art/characters/narrow.json
python3 -m tools.art build examples/art/characters/broad.json --godot --output .build/art/broad
```

The two manifests change cell, pivot, palette, shape, state, frame count, timing
and loop policy without changing the pipeline. See [art contracts and acceptance
limits](../../../docs/art.md). First-party fixture code and pixels use the root
[MIT license](../../../LICENSE). No external art, editor executable or model
service is required for these PNG inputs.
