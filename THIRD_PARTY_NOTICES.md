# Third-party notices

The toolkit's own license is in `LICENSE`. Third-party components retain their
own licenses; none is relicensed by this project.

## Dialogue Manager

- Author: Nathan Hoad
- Upstream: https://github.com/nathanhoad/godot_dialogue_manager
- Version: **3.10.4**, the upstream release for **Godot 4.6**
- Immutable commit: `5487c524b9eac303b059e5859e2980b134c59d79`
- License: MIT, copied verbatim into `licenses/DialogueManager-MIT.txt`

`scripts/fetch_dependencies.py` downloads and verifies the exact archive in
`deps.lock.json`, then installs only upstream `addons/dialogue_manager` into the
ignored `.deps/dialogue_manager` cache. The addon is not checked into this
toolkit's source tree. The prepared runnable example and its release archive
include the unmodified addon and its original `LICENSE`. This includes the
upstream editor UI and optional example assets, all covered by the upstream MIT
license. No separately sourced art, fonts, dialogue models, API clients, or paid
services are required.

The committed SHA-256 is the hash of the pinned commit archive retrieved from
GitHub's official codeload service. It is a reproducibility/integrity check, not
an upstream cryptographic signature.

## Godot Engine

- Authors: Godot Engine contributors; Juan Linietsky and Ariel Manzur
- Upstream: https://github.com/godotengine/godot
- Supported engine: **4.6.3-stable**, standard (non-.NET) build
- License: MIT, copied verbatim into `licenses/Godot-MIT.txt`

Godot is a build/runtime prerequisite, not bundled in this toolkit's source or
release archives. The optional Linux x86_64 installer obtains the official
release binary and verifies both SHA-256 from the official GitHub release asset
metadata and SHA-512 from the official `SHA512-SUMS.txt`. Exact provenance URLs
and hashes are committed in `deps.lock.json`. It writes only to `.deps/`.

Godot includes other third-party libraries with their own notices. If you
distribute an exported game or an engine binary, retain all required engine
notices, not just the short MIT license in this repository. Consult the official
copyright list and license guidance:

- https://github.com/godotengine/godot/blob/4.6.3-stable/COPYRIGHT.txt
- https://docs.godotengine.org/en/stable/about/complying_with_licenses.html

## CI tooling

The workflow uses the official `actions/checkout` v4.3.0 action, pinned to the
verified full commit `08eba0b27e820071cde6df949e0beb9ba4906955`. It is used only
inside GitHub Actions and is not included in release archives. Its license is
MIT: https://github.com/actions/checkout/blob/08eba0b27e820071cde6df949e0beb9ba4906955/LICENSE

CI uses the Ubuntu runner's Python standard library and the pinned Godot binary.
It requests read-only repository contents permission and needs no application
secrets, model credentials, paid API, export templates, or hosted model calls.

## Optional character art tooling

The small public art fixtures and Python/Lua/GDScript adapter/test code are
first-party MIT work. No private character artwork or Aseprite executable is
distributed. The optional Aseprite adapter invokes a user-provided licensed
installation; Aseprite is not a dependency of PNG processing or game runtime.
See [Aseprite licensing](https://www.aseprite.org/docs/license/) and
[art pipeline boundaries](docs/art.md). Source-art rights are declared per asset;
the code license does not grant rights to arbitrary input art.
