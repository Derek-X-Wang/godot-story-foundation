"""Deterministic local export/import/review/approval/build protocol.

Copyright (c) 2026 Derek Wang. MIT licensed. No network or model calls.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from . import __version__
from .simulation import simulate_fixtures
from .validation import ValidationError, require, validate_content, validate_packet, validate_exact_integers

MAX_BYTES = 2 * 1024 * 1024


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _pairs(pairs: list[tuple]) -> dict:
    obj = {}
    for key, value in pairs:
        require(key not in obj, "duplicate JSON key: " + key)
        obj[key] = value
    return obj


def load(path: str | Path) -> tuple[dict, str]:
    path = Path(path)
    require(path.stat().st_size <= MAX_BYTES, "input exceeds 2 MiB limit")
    raw = path.read_bytes()
    require(len(raw) <= MAX_BYTES, "input exceeds 2 MiB limit")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValidationError("non-finite JSON number")))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValidationError("invalid UTF-8 JSON: " + str(error)) from error
    require(isinstance(value, dict), "JSON root must be an object")
    validate_exact_integers(value)
    return value, digest(raw)


def _safe_output(path: str | Path) -> Path:
    target = Path(path).resolve()
    for parent in (target, *target.parents):
        require(not (parent / "project.godot").is_file(),
                "authoring outputs must remain outside a Godot project root; stage only compiled runtime files")
    return target


def write(path: str | Path, value: Any, *, raw: bool = False) -> None:
    target = _safe_output(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = value if raw else canonical(value)
    if isinstance(payload, str):
        payload = payload.encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix="." + target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _keys(value: dict, keys: set[str], label: str) -> None:
    require(set(value) == keys, f"{label}: missing or unknown fields")


def _metadata(value: str, label: str) -> None:
    require(isinstance(value, str) and 0 < len(value) <= 128 and value == value.strip()
            and all(ord(c) >= 32 and ord(c) != 127 for c in value), f"invalid {label}")


def _separate_output(output: str | Path, *sources: str | Path) -> None:
    target = Path(output).resolve()
    require(all(target != Path(source).resolve() for source in sources),
            "output must not overwrite an input file")


def export_request(packet_path: str | Path, output: str | Path) -> dict:
    _separate_output(output, packet_path)
    packet, packet_hash = load(packet_path)
    validate_packet(packet)
    from .validation import SCHEMA_ROOT
    content_schema = json.loads((SCHEMA_ROOT / "content.schema.json").read_text(encoding="utf-8"))
    request = {
        "schema_version":1, "kind":"provider_neutral_request", "tool_version":__version__,
        "packet_hash":packet_hash, "prompt_version":packet["prompt_version"],
        "instructions":[
            "Return exactly one JSON object conforming to response_schema. No Markdown, reasoning, or extra fields.",
            "Copy content_id, content_version, and world exactly from packet. Gameplay policy is human-authored.",
            "Write every required dialogue and branch. Include a fallback with no claims.",
            "Every factual claim annotation requires matching fact_eq and knows guards for the speaker.",
            "Use only registered identifiers and commands. Prose must be single-line plain text without markup. Choice text must not contain colons; speaker IDs must not start with else or elif.",
            "Do not include hidden reasoning, credentials, executable code, or unrelated world context.",
        ],
        "packet":packet, "response_schema":content_schema,
    }
    write(output, request)
    return request


def import_response(packet_path: str | Path, response_path: str | Path,
                    model_declared: str, output: str | Path) -> dict:
    _separate_output(output, packet_path, response_path)
    packet, packet_hash = load(packet_path)
    response, response_hash = load(response_path)
    _metadata(model_declared, "declared model")
    validate_content(packet, response)
    simulate_fixtures(packet, response)
    candidate = {
        "schema_version":1, "kind":"unapproved_candidate", "tool_version":__version__,
        "packet_hash":packet_hash, "prompt_version":packet["prompt_version"],
        "model_declared":model_declared, "response_hash":response_hash,
        "content_hash":digest(canonical(response)), "content":response,
    }
    write(output, candidate)
    return candidate


def inputs(packet_path: str | Path, candidate_path: str | Path) -> tuple[dict, dict, str, str, dict]:
    packet, packet_hash = load(packet_path)
    candidate, candidate_hash = load(candidate_path)
    _keys(candidate, {"schema_version","kind","tool_version","packet_hash","prompt_version",
                      "model_declared","response_hash","content_hash","content"}, "candidate")
    require(type(candidate["schema_version"]) is int and candidate["schema_version"] == 1,
            "unsupported candidate schema")
    require(candidate["kind"] == "unapproved_candidate", "invalid candidate kind")
    require(candidate["tool_version"] == __version__, "candidate tool version mismatch; re-import")
    require(candidate["packet_hash"] == packet_hash, "packet changed since response import")
    require(candidate["prompt_version"] == packet["prompt_version"], "candidate prompt version mismatch")
    _metadata(candidate["model_declared"], "declared model")
    require(isinstance(candidate["response_hash"], str) and len(candidate["response_hash"]) == 64
            and all(c in "0123456789abcdef" for c in candidate["response_hash"]), "invalid response hash")
    require(candidate["content_hash"] == digest(canonical(candidate["content"])), "candidate content hash mismatch")
    validate_content(packet, candidate["content"])
    simulation = simulate_fixtures(packet, candidate["content"])
    return packet, candidate, packet_hash, candidate_hash, simulation


def validate_candidate(packet_path: str | Path, candidate_path: str | Path) -> dict:
    _, _, packet_hash, candidate_hash, simulation = inputs(packet_path, candidate_path)
    return {"valid":True, "packet_hash":packet_hash, "candidate_hash":candidate_hash,
            "simulation":simulation}


def create_review(packet_path: str | Path, candidate_path: str | Path, output: str | Path,
                  baseline_path: str | Path | None = None) -> dict:
    _separate_output(output, packet_path, candidate_path, *([baseline_path] if baseline_path else []))
    readable_path = Path(output).with_suffix(".txt")
    require(readable_path.resolve() != Path(output).resolve(), "review output must not use the .txt suffix")
    _separate_output(readable_path, packet_path, candidate_path, *([baseline_path] if baseline_path else []))
    _safe_output(output)
    _safe_output(readable_path)
    packet, candidate, packet_hash, candidate_hash, simulation = inputs(packet_path, candidate_path)
    baseline = {}
    baseline_hash = None
    if baseline_path:
        baseline, baseline_hash = load(baseline_path)
    difference = "".join(difflib.unified_diff(
        canonical(baseline).decode().splitlines(keepends=True) if baseline_path else [],
        canonical(candidate["content"]).decode().splitlines(keepends=True),
        fromfile="previous-content.json" if baseline_path else "empty-baseline",
        tofile="candidate-content.json"))
    report = {
        "schema_version":1, "kind":"review_report", "tool_version":__version__,
        "packet_hash":packet_hash, "candidate_hash":candidate_hash,
        "baseline_hash":baseline_hash, "prompt_version":packet["prompt_version"],
        "model_declared":candidate["model_declared"], "validation_passed":True,
        "simulation":simulation, "diff":difference,
        "review_notes":[
            "NOT APPROVED. Read the complete packet, candidate, diff, and simulation before manual approval.",
            "Gameplay policy is identical to the packet; the importer cannot modify it.",
            "Knowledge annotations are machine-checked. A human must verify that all prose claims are annotated and honest.",
            "Fixture coverage covers named final branches, not every possible state or all artistic quality.",
        ],
    }
    write(output, report)
    text = "OFFLINE AUTHORING REVIEW — NOT APPROVED\n"
    text += f"Packet SHA-256: {packet_hash}\nCandidate SHA-256: {candidate_hash}\n"
    text += f"Declared model: {candidate['model_declared']} (caller-supplied; not independently verified)\n"
    text += f"Fixtures: {len(simulation['fixtures'])} passed; branches: {simulation['coverage']['covered_count']}/{simulation['coverage']['required_count']}\n\n"
    text += "\n".join(report["review_notes"]) + "\n\n" + difference
    text += "\nSIMULATION\n" + canonical(simulation).decode()
    write(readable_path, text, raw=True)
    return report


def _checked_review(review_path: str | Path, packet_hash: str, candidate_hash: str,
                    simulation: dict, packet: dict, candidate: dict) -> tuple[dict, str]:
    review, review_hash = load(review_path)
    _keys(review, {"schema_version","kind","tool_version","packet_hash","candidate_hash",
                   "baseline_hash","prompt_version","model_declared","validation_passed",
                   "simulation","diff","review_notes"}, "review")
    require(type(review["schema_version"]) is int and review["schema_version"] == 1, "invalid review schema")
    require(review["kind"] == "review_report" and review["tool_version"] == __version__, "invalid review version")
    require(review["packet_hash"] == packet_hash and review["candidate_hash"] == candidate_hash,
            "stale review: packet or candidate changed")
    require(review["validation_passed"] is True and review["simulation"] == simulation,
            "review simulation does not match current validation")
    require(review["prompt_version"] == packet["prompt_version"]
            and review["model_declared"] == candidate["model_declared"], "review metadata mismatch")
    require(isinstance(review["diff"], str) and isinstance(review["review_notes"], list), "invalid review text")
    return review, review_hash


def approve(packet_path: str | Path, candidate_path: str | Path, review_path: str | Path,
            reviewer: str, affirmative: bool, output: str | Path) -> dict:
    _separate_output(output, packet_path, candidate_path, review_path)
    require(affirmative is True, "manual approval requires --yes-i-reviewed")
    _metadata(reviewer, "reviewer identity")
    packet, candidate, packet_hash, candidate_hash, simulation = inputs(packet_path, candidate_path)
    _, review_hash = _checked_review(review_path, packet_hash, candidate_hash, simulation, packet, candidate)
    approval = {
        "schema_version":1, "kind":"human_approval", "tool_version":__version__,
        "review_status":"approved", "reviewer":reviewer, "test_fixture":False,
        "packet_hash":packet_hash, "candidate_hash":candidate_hash, "review_hash":review_hash,
    }
    write(output, approval)
    return approval


def dialogue_manager_source(content: dict) -> str:
    """Only fixed adapter calls are emitted; text has already passed safe_prose."""
    lines = ["# Generated from approved static content. Do not edit; rebuild instead.", ""]
    for dialogue in content["dialogues"]:
        did = dialogue["id"]
        lines.append("~ " + did)
        for index, branch in enumerate(dialogue["branches"] + [dialogue["fallback"]]):
            if index < len(dialogue["branches"]):
                keyword = "if" if index == 0 else "elif"
                lines.append(f'{keyword} story.branch_available("{did}", "{branch["id"]}")')
            else:
                lines.append("else")
            lines.append("\t" + dialogue["speaker"] + ": " + branch["text"])
            for choice in branch["choices"]:
                lines.append("\t- " + choice["text"])
                lines.append(f'\t\tdo story.choose("{did}", "{branch["id"]}", "{choice["id"]}")')
                lines.append("\t\t=> END")
            lines.append("\t=> END")
        lines.extend(["=> END", ""])
    return "\n".join(lines)


def build(packet_path: str | Path, candidate_path: str | Path, review_path: str | Path,
          approval_path: str | Path, output: str | Path, allow_test_fixture: bool = False) -> dict:
    packet, candidate, packet_hash, candidate_hash, simulation = inputs(packet_path, candidate_path)
    _, review_hash = _checked_review(review_path, packet_hash, candidate_hash, simulation, packet, candidate)
    approval, approval_hash = load(approval_path)
    _keys(approval, {"schema_version","kind","tool_version","review_status","reviewer","test_fixture",
                     "packet_hash","candidate_hash","review_hash"}, "approval")
    require(type(approval["schema_version"]) is int and approval["schema_version"] == 1, "invalid approval schema")
    require(approval["tool_version"] == __version__, "approval tool version changed; re-review")
    require(approval["review_status"] == "approved", "candidate is not approved")
    require(type(approval["test_fixture"]) is bool, "invalid fixture approval flag")
    _metadata(approval["reviewer"], "reviewer identity")
    if approval["test_fixture"]:
        require(approval["kind"] == "synthetic_test_approval", "invalid synthetic approval kind")
        require(allow_test_fixture, "synthetic approval requires --allow-test-fixture; this is not human approval")
    else:
        require(approval["kind"] == "human_approval", "invalid human approval kind")
    require(approval["packet_hash"] == packet_hash and approval["candidate_hash"] == candidate_hash
            and approval["review_hash"] == review_hash,
            "approval invalidated: exact packet, candidate, or review bytes changed")
    target = _safe_output(output)
    for filename in ("content.json", "presentation.dialogue", "build-manifest.json", "audit.json"):
        _separate_output(target / filename, packet_path, candidate_path, review_path, approval_path)
    artifacts = {"content.json":canonical(candidate["content"]),
                 "presentation.dialogue":dialogue_manager_source(candidate["content"]).encode("utf-8")}
    artifact_hashes = {name:digest(data) for name,data in artifacts.items()}
    manifest = {
        "schema_version":1, "tool_version":__version__, "content_id":packet["content_id"],
        "content_version":packet["content_version"], "artifacts":artifact_hashes,
        "test_fixture":approval["test_fixture"],
    }
    audit = {
        "schema_version":1, "tool_version":__version__, "prompt_version":packet["prompt_version"],
        "model_declared":candidate["model_declared"], "model_provenance":"caller_declared_not_verified",
        "input_hashes":{"packet":packet_hash,"candidate":candidate_hash,"response":candidate["response_hash"],
                        "review":review_hash,"approval":approval_hash},
        "output_hashes":artifact_hashes, "review_status":"synthetic_test_fixture" if approval["test_fixture"] else "human_approved",
        "reviewer":approval["reviewer"],
    }
    # All validation finishes before any output is written.
    for name, data in artifacts.items():
        write(target / name, data, raw=True)
    write(target / "build-manifest.json", manifest)
    write(target / "audit.json", audit)
    return manifest
