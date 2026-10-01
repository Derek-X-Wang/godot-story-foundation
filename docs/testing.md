# Verification and release checks

The release targets Godot 4.6.3 and the pinned official Dialogue Manager 3.10.4.
Run the complete command sequence in the README after changes, including a fresh
project import. Python checks require no network or third-party packages.

Local final verification on 2026-10-01: **103 Python tests, 7 optional Godot
serializer tests, 118 native runtime checks and 43 real Dialogue Manager/native
fixture checks passed**. The extracted
release bundle repeats runtime/dialogue checks and imports cleanly. These are
local results; hosted CI is verified separately for the published commit.

Optional character-art verification on 2026-10-01 additionally passed:

- 247 Godot import/pixel/geometry/timing/playback checks in each of two fresh
  projects, including relocation after removing the original project
- 47 real Aseprite 1.3.18.6 CLI/Lua checks: two synthetic drawings plus indexed variant, PNG/native
  equivalence, deterministic output, source preservation and rejection paths
- A private 24-frame indexed production source through the same adapter, without
  publishing its artwork or changing its source/playback policy

The public CI runs PNG/manifest tests and the standalone Godot consumer tests.
It does not install a licensed Aseprite binary; run the documented optional test
locally. The real second character is still awaiting appearance approval/native
authoring; synthetic tests are not its art acceptance. See [art checks](art.md).

Coverage includes:

- The original 46 native rule regressions, then portable APIs, copied queries,
  generic inventory/scenes, guarded commands, declared save facts and numeric bounds
- Actual Dialogue Manager import, conditional line/response traversal, choice
  mutations, stale/repeated buttons, resource cleanup, and replay of the same
  declared fixtures used by the Python simulator
- Packet/candidate/reference validation, missing fallback and branch coverage,
  safe DSL generation, input/candidate/review mutation invalidation, synthetic
  fixture opt-in, deterministic builds, and schema/CLI failure cases
- Download size and checksum validation, ZIP path/symlink rejection, package
  allowlisting and deterministic archives

A Linux cloud-desktop walkthrough exercised honest ignorance, unavailable choice,
private observation, shared knowledge, path marking and reward, then save,
restart and load. Headless startup independently checks the main scene. These
checks do not establish a frame-rate target or portability to another OS.

Before publishing a release:

1. Run all checks against the exact final source
2. Rebuild twice and compare archive bytes and SHA-256
3. Inspect the package manifest and extract/import it in a fresh project
4. Confirm authoring/review data, caches, binaries and credentials are absent
5. Verify the hosted CI run for the published commit, rather than assuming local
   success proves remote CI
6. Record the source tag/commit and package SHA-256 in consuming games

Not run by this repository's CI: paid/live model generation, production human
review, export-template builds, platform exports, web/mobile execution or networked
multiplayer. Review approvals use exact file hashes and explicit CLI affirmation;
the synthetic test fixture is not evidence of a human reviewing production prose.
