#!/usr/bin/env python3
"""Start a consumer workspace and check declared production review evidence.

MIT License

Copyright (c) 2026 Derek Wang

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
No engine, network, model, image analysis or automatic visual approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import shutil
import sys
import tempfile

GATES = ("flow", "brief", "composition", "integration", "release")
REVIEW_GATES = GATES[2:]
KINDS = {"rendered_still", "rendered_sequence", "playback", "check_report"}

AGENT_GUIDE = """# Production guardrails for this game

Before implementing or resuming work, read authoring/production.json and run:

    python3 tools/production.py check authoring/production.json --gate flow

Before visual design or asset production, complete the production brief and run --gate brief.
Before expanding the art batch, inspect a small actual rendered playable slice
and close --gate composition. Before claiming integrated, close --gate integration;
before claiming release-ready, close --gate release against the final candidate.
Flow-only work may proceed without art approval; say that it is flow-only.

- Declare this game's representation convention before judging proportions.
  Symbolic/tile RPGs need internal logic, not literal building-to-person ratios.
  Perspective scenes need coherent depth-dependent world scale, grounded feet,
  contact/occlusion and stable object position/custody. Check movement endpoints
  and intermediate frames. Prefer an honest pose cut to an unconvincing animation.
- Separate foreground dialogue portraits/UI from actors inside the world.
  Do not inherit prototype flow buttons or layout as the final presentation.
  Specify dialogue advancement, choices and portrait use for this game; no format
  is universal. Inspect long text, blocked input and essential cue visibility.
- A hidden/offscreen sampler, loaded asset, headless Label assertion or successful
  export is not evidence that the player saw an event. Inspect actual composition
  at the declared viewports; play motion and transitions, not just endpoint stills.
- Record provisional/missing assets honestly. Do not mark visual acceptance from
  automated checks. Keep reviewer decisions, rendered evidence and automated
  results separate; passing the checker validates records, not their truth.
- Keep source/build identities current. Changed brief/revision or evidence needs
  renewed review. Do not update hashes merely to conceal a stale approval.
- Keep authoring sources, private reviews and captures outside game/, the intended
  export root. Install only selected runtime modules; this is not a required engine.

## Completing a record

Run tools/production.py from this workspace. Fill reference kind as local,
external or none. Local source paths are relative to authoring/ and identity is
that file's SHA-256. External identity pins an exact version/hash; it is not fetched.
Use none only with status not_applicable and a reason in use. Resolve provisional
references before final asset integration. UI and movement fields describe this
game's decisions, not universal formats. List representative viewports/states.

For each rendered/check artifact, retain its SHA-256 and the candidate_sha256
from `identity authoring/production.json --gate composition` at capture time.
Evidence kinds are rendered_still, rendered_sequence, playback or check_report.
Use a rendered sequence/playback for movement or cuts, not endpoint stills alone.
Cover every declared viewport/state pair; one genuine sequence may be referenced
for several targets it actually shows. Paths must remain beneath authoring/.

Before final identity, fill the reviewer, reviewer_kind (human or agent),
reviewed_at, scope, evidence and checks. `identity` prints candidate_revision,
candidate_sha256 and basis_sha256 to copy into that review; it never approves.
Record the actual decision separately. Check entries name the lane, result and
an evidence_path pointing to a hashed check_report. Blocked/failed/unrun lanes
cannot close the gate. Do not omit applicable failures. Review evidence and local
reference bytes are verified, but provenance and review truth remain human/agent
responsibilities. Never represent agent review as the owner's approval.

The candidate_path is workspace-relative and must exclude authoring/. Fingerprints
include dirty/untracked files, excluding only .git/.godot directories. Include
built deliverables when claiming a packed build; source hashes do not cover an
external pack automatically. Keep the candidate frozen while capturing/checking.
Earlier composition remains historical direction after source changes, but each
new integration/release candidate needs fresh evidence with its own fingerprint.

Use python3 tools/production.py --help for the local, dependency-free checker.
Keep game-specific rules here. Do not relax an unresolved gate silently; report
its exact failure, scope and next action instead of asking the user to rediscover it.
"""


def template() -> dict:
    return {
        "schema_version": 1, "test_fixture": False,
        "project": "", "scope": "", "revision": "", "candidate_path": "game",
        "assets": [],
        "references": {
            role: {"source": "", "kind": "external", "identity": "", "status": "provisional", "use": ""}
            for role in ("flow", "art", "composition")
        },
        "presentation": {
            "convention": "", "rationale": "", "viewports": [], "states": [],
            "world_scale": "", "grounding_occlusion": "", "continuity": "",
            "movement": {"mode": "", "depth_policy": ""},
            "ui": {"portraits": "", "dialogue_and_choices": "", "essential_visibility": ""},
        },
        "reviews": {
            gate: {"decision": "pending", "reviewer": "", "reviewer_kind": "", "reviewed_at": "", "scope": "",
                   "candidate_revision": "", "candidate_sha256": "",
                   "basis_sha256": "",
                   "evidence": [{"path": "", "sha256": "", "candidate_sha256": "", "kind": "",
                                 "scope": "", "platform": "", "viewport": "", "route_state": ""}],
                   "checks": [] if gate == "composition" else [{"name": "", "result": "unrun", "evidence_path": ""}]}
            for gate in REVIEW_GATES
        },
    }


class Invalid(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Invalid(message)


def obj(value, label: str) -> dict:
    require(isinstance(value, dict), f"{label}: expected an object")
    return value


def filled(value, label: str) -> None:
    require(isinstance(value, str) and bool(value.strip()), f"{label}: fill in this decision or explain why it does not apply")


def canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load(path: Path) -> dict:
    require(path.stat().st_size <= 1024 * 1024, "production record exceeds 1 MiB")
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicates,
                      parse_constant=lambda _: (_ for _ in ()).throw(Invalid("non-finite JSON number")))
    return obj(data, "production record")


def identity(data: dict, gate: str) -> str:
    review = obj(obj(data.get("reviews"), "reviews").get(gate), f"reviews.{gate}")
    # Direction survives unrelated source changes. A later gate still needs its
    # own current candidate fingerprint and rendered evidence.
    basis = {key: data.get(key) for key in ("schema_version", "test_fixture", "project", "scope", "references", "presentation")}
    basis["review"] = {key: review.get(key) for key in ("reviewer", "reviewer_kind", "reviewed_at", "scope", "candidate_revision", "candidate_sha256", "evidence", "checks")}
    if gate != "composition":
        basis["assets"] = data.get("assets")
    basis["gate"] = gate
    return hashlib.sha256(canonical(basis)).hexdigest()


def candidate_digest(data: dict, authoring: Path) -> str:
    workspace = authoring.resolve().parent
    filled(data.get("candidate_path"), "candidate_path")
    relative = Path(data["candidate_path"])
    require(not relative.is_absolute() and ".." not in relative.parts, "candidate_path: use a workspace-relative directory")
    root = (workspace / relative).resolve()
    require(root.is_relative_to(workspace) and root.is_dir(), "candidate_path: missing or outside workspace")
    require(not authoring.resolve().is_relative_to(root), "candidate_path: must exclude the authoring/review directory")
    require((workspace / relative).absolute() == root, "candidate_path: symlink paths/ancestors are not supported")
    entries = []
    def visit(directory):
        for path in sorted(directory.iterdir()):
            # Only Git internals and Godot's regenerable import cache are excluded.
            if path.name in {".git", ".godot"}:
                continue
            require(not path.is_symlink(), "candidate_path: symlink inputs are not supported")
            if path.is_dir():
                visit(path)
            else:
                require(path.is_file(), "candidate_path: expected regular files only")
                with path.open("rb") as stream:
                    entries.append((path.relative_to(root).as_posix(), hashlib.file_digest(stream, "sha256").hexdigest()))
    visit(root)
    require(bool(entries), "candidate_path: candidate has no source/build files")
    return hashlib.sha256(canonical(entries)).hexdigest()


def artifact(root: Path, record: dict, label: str) -> None:
    filled(record.get("path"), f"{label}.path")
    relative = Path(record["path"])
    require(not relative.is_absolute() and ".." not in relative.parts,
            f"{label}.path: use a path beneath the production record's directory")
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()) and path.is_file(),
            f"{label}.path: missing file or path escapes authoring storage")
    expected = record.get("sha256")
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    require(expected == actual, f"{label}.sha256: evidence bytes changed; inspect and review the new artifact")


def check(data: dict, root: Path, gate: str, allow_test_fixture: bool = False) -> None:
    require(gate in GATES, "unknown gate")
    require(type(data.get("schema_version")) is int and data["schema_version"] == 1, "schema_version: expected 1")
    require(type(data.get("test_fixture")) is bool, "test_fixture: declare true or false")
    require(not data["test_fixture"] or allow_test_fixture,
            "synthetic fixture is not production approval; use --allow-test-fixture only for demonstration/tests")
    for field in ("project", "scope", "revision"):
        filled(data.get(field), field)
    references = obj(data.get("references"), "references")
    for role in (("flow",) if gate == "flow" else ("flow", "art", "composition")):
        ref = obj(references.get(role), f"references.{role}")
        for field in ("source", "identity", "use"):
            filled(ref.get(field), f"references.{role}.{field}")
        require(ref.get("kind") in {"local", "external", "none"}, f"references.{role}.kind: choose local, external or none")
        if ref["kind"] == "local":
            artifact(root, {"path": ref["source"], "sha256": ref["identity"]}, f"references.{role}")
        require((ref["kind"] == "none") == (ref.get("status") == "not_applicable"), f"references.{role}: kind none requires status not_applicable and a reason in use")
        if gate in {"integration", "release"}:
            require(ref.get("status") != "provisional", f"references.{role}: resolve provisional direction before final asset integration")
        require(ref.get("status") in {"accepted", "provisional", "not_applicable"},
                f"references.{role}.status: choose accepted, provisional or not_applicable; explain the role in use")
    if gate == "flow":
        return
    p = obj(data.get("presentation"), "presentation")
    require(p.get("convention") in {"symbolic_grid", "scene_perspective", "custom"},
            "presentation.convention: choose symbolic_grid, scene_perspective or custom")
    for field in ("rationale", "world_scale", "grounding_occlusion", "continuity"):
        filled(p.get(field), f"presentation.{field}")
    require(isinstance(p.get("viewports"), list) and bool(p["viewports"]), "presentation.viewports: list the target viewports")
    for field in ("viewports", "states"):
        require(isinstance(p.get(field), list) and bool(p[field]), f"presentation.{field}: list the reviewed targets")
        for target in p[field]:
            filled(target, f"presentation.{field} entry")
        require(len(p[field]) == len(set(p[field])), f"presentation.{field}: duplicate targets")
    movement = obj(p.get("movement"), "presentation.movement")
    require(movement.get("mode") in {"animated", "pose_cut", "none", "mixed"},
            "presentation.movement.mode: choose animated, pose_cut, none or mixed")
    filled(movement.get("depth_policy"), "presentation.movement.depth_policy")
    ui = obj(p.get("ui"), "presentation.ui")
    for field in ("portraits", "dialogue_and_choices", "essential_visibility"):
        filled(ui.get(field), f"presentation.ui.{field}")
    if gate == "brief":
        return
    assets = data.get("assets")
    require(isinstance(assets, list) and bool(assets), "assets: declare the selected assets and maturity before composition review")
    asset_ids = set()
    for asset in assets:
        obj(asset, "assets entry")
        for field in ("id", "note"):
            filled(asset.get(field), f"assets.{field}")
        require(asset["id"] not in asset_ids, "assets: duplicate id")
        asset_ids.add(asset["id"])
        require(asset.get("status") in {"placeholder", "candidate", "accepted"}, "assets.status: choose placeholder, candidate or accepted")
        if gate in {"integration", "release"}:
            require(asset["status"] == "accepted", "assets: placeholder/candidate acceptance cannot stand in for integrated final assets; limit the declared scope or finish review")
    current_candidate = candidate_digest(data, root)
    reviews = obj(data.get("reviews"), "reviews")
    for stage in REVIEW_GATES[:REVIEW_GATES.index(gate) + 1]:
        label = f"reviews.{stage}"
        review = obj(reviews.get(stage), label)
        require(review.get("decision") == "accepted", f"{label}.decision: obtain explicit acceptance for this scope, not an automatic pass")
        for field in ("reviewer", "reviewed_at", "scope", "candidate_revision"):
            filled(review.get(field), f"{label}.{field}")
        require(review.get("reviewer_kind") in {"human", "agent", "synthetic"}, f"{label}.reviewer_kind: declare human, agent or synthetic")
        require(review["reviewer_kind"] != "synthetic" or data["test_fixture"], f"{label}: synthetic reviewer cannot approve production")
        require(isinstance(review.get("candidate_sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", review["candidate_sha256"]), f"{label}.candidate_sha256: provide a candidate fingerprint")
        if stage == gate:
            require(review["candidate_revision"] == data["revision"] and review["candidate_sha256"] == current_candidate,
                    f"{label}: candidate source/build changed, including dirty/untracked files; inspect the current candidate and renew this gate")
        evidence = review.get("evidence")
        require(isinstance(evidence, list) and bool(evidence), f"{label}.evidence: attach current rendered evidence")
        kinds, paths, targets = set(), set(), set()
        for item in evidence:
            obj(item, f"{label}.evidence entry")
            require(item.get("kind") in KINDS, f"{label}.evidence.kind: use rendered_still, rendered_sequence, playback or check_report; hidden samplers are not rendered evidence")
            for field in ("scope", "platform", "viewport", "route_state"):
                filled(item.get(field), f"{label}.evidence.{field}")
            if item["kind"] != "check_report":
                require(item["viewport"] in p["viewports"] and item["route_state"] in p["states"], f"{label}.evidence: viewport/state is outside declared targets")
                targets.add((item["viewport"], item["route_state"]))
            require(item.get("candidate_sha256") == review["candidate_sha256"], f"{label}.evidence: capture/report belongs to a different candidate; do not rebind old evidence")
            artifact(root, item, f"{label}.evidence")
            key = (item["path"], item["viewport"], item["route_state"])
            require(key not in paths, f"{label}.evidence: duplicate artifact/target entry")
            kinds.add(item["kind"])
            paths.add(key)
        require(kinds & {"rendered_still", "rendered_sequence", "playback"}, f"{label}: headless/check reports cannot replace rendered evidence")
        require(targets == {(v, state) for v in p["viewports"] for state in p["states"]}, f"{label}: rendered evidence must cover every declared viewport/state pair")
        if movement["mode"] != "none":
            require(kinds & {"rendered_sequence", "playback"}, f"{label}: movement/cuts need playback or a rendered sequence, not endpoint stills alone")
        checks = review.get("checks")
        require(isinstance(checks, list), f"{label}.checks: expected a list")
        if stage in {"integration", "release"}:
            require(bool(checks), f"{label}.checks: record applicable focused/final checks and their evidence")
        for result in checks:
            obj(result, f"{label}.checks entry")
            filled(result.get("name"), f"{label}.checks.name")
            require(result.get("result") == "passed", f"{label}.checks: a failed, blocked or unrun check cannot close this gate")
            require(result.get("evidence_path") in {e["path"] for e in evidence if e["kind"] == "check_report"},
                    f"{label}.checks.evidence_path: reference a hashed check_report artifact")
        require(review.get("basis_sha256") == identity(data, stage),
                f"{label}.basis_sha256: stale/missing review binding; re-review changed scope, revision and evidence, then run identity --gate {stage}")


def start(output: Path) -> None:
    output = output.parent.resolve() / output.name
    require(not output.exists() and not output.is_symlink(), "output already exists; choose a fresh workspace (existing files are never overwritten)")
    require(output.parent.is_dir(), "output parent must exist")
    require(not any((p / "project.godot").is_file() for p in (output.parent, *output.parent.parents)),
            "create the workspace outside a Godot project/export root")
    stage = Path(tempfile.mkdtemp(prefix=".production-", dir=output.parent))
    try:
        (stage / "authoring").mkdir()
        (stage / "tools").mkdir()
        (stage / "game").mkdir()
        (stage / "AGENTS.md").write_text(AGENT_GUIDE, encoding="utf-8")
        (stage / "authoring/production.json").write_bytes(canonical(template()))
        shutil.copyfile(Path(__file__), stage / "tools/production.py")
        (stage / "game/README.md").write_text("Place selected runtime modules and approved runtime assets here.\nKeep production records and captures in ../authoring, outside this export root.\n", encoding="utf-8")
        # No engine project, dependency fetch, credentials or accepted review is created.
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="create a fresh consumer workspace with startup guardrails")
    init.add_argument("--output", type=Path, required=True)
    for command in ("check", "identity"):
        part = sub.add_parser(command)
        part.add_argument("record", type=Path)
        part.add_argument("--gate", choices=GATES if command == "check" else REVIEW_GATES, required=True)
        if command == "check":
            part.add_argument("--allow-test-fixture", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            start(args.output)
            print(f"Created {args.output}. Read AGENTS.md and fill authoring/production.json; no gate is accepted yet.")
        else:
            data = load(args.record)
            if args.command == "identity":
                review = obj(obj(data.get("reviews"), "reviews").get(args.gate), "review")
                review["candidate_sha256"] = candidate_digest(data, args.record.parent)
                review["candidate_revision"] = data.get("revision")
                print(json.dumps({"candidate_revision": review["candidate_revision"], "candidate_sha256": review["candidate_sha256"], "basis_sha256": identity(data, args.gate)}, indent=2))
            else:
                check(data, args.record.parent, args.gate, args.allow_test_fixture)
                print(f"{args.gate}: declared records/evidence valid; not automatic visual approval or proof of review truth.")
        return 0
    except (Invalid, OSError, UnicodeError, ValueError, TypeError, RecursionError) as error:
        print(f"Production gate blocked: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
