"""Experimental audience-first playtest records. Offline, standard-library only.

Records and references are caller-declared evidence, not authenticated proof.
This module never calls a model, executes a game, reads referenced files, or votes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

VERSION = 1
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_REPORTS = 256
MAX_ITEMS = 4096
MAX_TEXT = 16384
MAX_NUMBER = 10 ** 12
MODES = ("natural", "chapter", "targeted")
SEGMENTS = ("core", "adjacent", "non_target")
FIDELITY = ("actual_engine_observations", "choice_roundtrip_verified",
            "feedback_before_outcome", "blind_inputs_only", "vanilla_controls_preserved")


class ContractError(ValueError):
    """A record is malformed, inconsistent, or belongs to a different round."""


def require(ok, message):
    if not ok:
        raise ContractError(message)


def obj(value, fields, at, optional=()):
    require(type(value) is dict, f"{at}: expected object")
    require(not set(value) - set(fields) - set(optional), f"{at}: unknown fields")
    require(not set(fields) - set(value), f"{at}: missing fields")
    return value


def array(value, at, nonempty=False):
    require(type(value) is list and len(value) <= MAX_ITEMS and (not nonempty or bool(value)), f"{at}: expected array")
    return value


def string(value, at):
    require(type(value) is str and len(value) <= MAX_TEXT and bool(value.strip()), f"{at}: expected nonempty text")
    return value


def ident(value, at):
    require(type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value),
            f"{at}: invalid identifier")
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def sha(value, at):
    require(type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value), f"{at}: expected SHA256")


def number(value, at, integer=False, minimum=0):
    require(type(value) in ((int,) if integer else (int, float))
            and minimum <= value <= MAX_NUMBER
            and (type(value) is int or math.isfinite(value)), f"{at}: invalid number")


def enum(value, choices, at):
    require(type(value) is str and value in choices, f"{at}: expected one of {choices}")


def unique(values, at):
    require(len(values) == len(set(values)), f"{at}: duplicate values")


def strings(value, at, choices=None, nonempty=False):
    for item in array(value, at, nonempty):
        string(item, at)
        if choices is not None:
            require(item in choices, f"{at}: unknown reference {item}")
    unique(value, at)


def indexed(value, at, nonempty=True):
    result = {}
    for item in array(value, at, nonempty):
        require(type(item) is dict, f"{at}: expected object entries")
        key = ident(item.get("id"), at)
        require(key not in result, f"{at}: duplicate id {key}")
        result[key] = item
    return result


def load(path):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, f"duplicate JSON key: {key}")
            out[key] = value
        return out
    def constant(value):
        raise ContractError(f"non-finite JSON number: {value}")
    # Check the opened descriptor without blocking on pipes or following symlinks.
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "input must be a regular file")
        raw = stream.read(MAX_DOCUMENT_BYTES + 1)
    require(len(raw) <= MAX_DOCUMENT_BYTES, "input exceeds byte limit")
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    pending = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        require(depth <= 32, "input exceeds nesting limit")
        if type(item) is dict:
            require(len(item) <= MAX_ITEMS, "object exceeds item limit")
            pending.extend((v, depth + 1) for v in item.values())
        elif type(item) is list:
            array(item, "input")
            pending.extend((v, depth + 1) for v in item)
        elif type(item) is str:
            require(len(item) <= MAX_TEXT, "input exceeds string limit")
    return value


def validate_round(value):
    obj(value, ("schema_version", "id", "candidate", "audience", "axes", "profiles",
                "models", "scenarios", "questions", "budget", "starting_point"), "round")
    require(type(value["schema_version"]) is int and value["schema_version"] == VERSION,
            "round: unsupported schema_version")
    ident(value["id"], "round.id")
    obj(value["candidate"], ("id", "build_sha256", "engine", "adapter"), "candidate")
    for key in ("id", "engine", "adapter"):
        string(value["candidate"][key], "candidate." + key)
    sha(value["candidate"]["build_sha256"], "candidate.build_sha256")
    obj(value["audience"], ("core", "adjacent", "non_target", "intended_experience"), "audience")
    for key, text in value["audience"].items():
        string(text, "audience." + key)
    axes = indexed(value["axes"], "axes")
    for axis in axes.values():
        obj(axis, ("id", "reason", "values", "relevant_values"), "axis")
        string(axis["reason"], "axis.reason")
        strings(axis["values"], "axis.values", nonempty=True)
        strings(axis["relevant_values"], "axis.relevant_values", axis["values"], True)
    profiles = indexed(value["profiles"], "profiles")
    for profile in profiles.values():
        obj(profile, ("id", "segment", "role", "preferences", "rationale"), "profile")
        enum(profile["segment"], SEGMENTS, "profile.segment")
        enum(profile["role"], ("motivated", "neutral"), "profile.role")
        string(profile["rationale"], "profile.rationale")
        require(type(profile["preferences"]) is dict, "profile.preferences: expected object")
        if profile["role"] == "neutral":
            require(not profile["preferences"], "neutral profile must have no imposed preferences")
        else:
            require(bool(profile["preferences"]), "motivated profile needs preferences")
        for axis_id, preference in profile["preferences"].items():
            require(axis_id in axes, "profile: unknown axis")
            enum(preference, axes[axis_id]["values"], "profile.preference")
    require(any(p["segment"] == "core" and p["role"] == "motivated" for p in profiles.values()),
            "round needs at least one intended-audience motivated profile")
    models = indexed(value["models"], "models")
    for model in models.values():
        obj(model, ("id", "model", "configuration", "provenance"), "model")
        for key in ("model", "configuration", "provenance"):
            string(model[key], "model." + key)
    scenarios = indexed(value["scenarios"], "scenarios")
    for scenario in scenarios.values():
        obj(scenario, ("id", "description"), "scenario")
        string(scenario["description"], "scenario.description")
    for question in indexed(value["questions"], "questions").values():
        obj(question, ("id", "question", "next_decision", "scenarios", "modes", "segments"), "question")
        for key in ("question", "next_decision"):
            string(question[key], "question." + key)
        strings(question["scenarios"], "question.scenarios", scenarios, True)
        strings(question["modes"], "question.modes", MODES, True)
        strings(question["segments"], "question.segments", SEGMENTS, True)
        require("non_target" not in question["segments"],
                "non-target diagnostics cannot answer intended-audience round questions")
    obj(value["budget"], ("max_sessions", "max_total_minutes", "max_session_minutes", "max_turns"), "budget")
    for key, amount in value["budget"].items():
        number(amount, "budget." + key, integer=key in ("max_sessions", "max_turns"), minimum=1)
    enum(value["starting_point"], ("narrow_segment", "new_demo", "custom"), "starting_point")
    return value


def plan(round_record):
    r = validate_round(round_record)
    gaps = []
    for axis in r["axes"]:
        covered = {p["preferences"].get(axis["id"]) for p in r["profiles"] if p["segment"] == "core"}
        for preference in axis["relevant_values"]:
            if preference not in covered:
                gaps.append({"axis": axis["id"], "value": preference})
    return {"schema_version": VERSION, "status": "planned", "experimental": True,
            "round_sha256": digest(r), "profile_count": len(r["profiles"]),
            "profiles_by_segment": dict(Counter(p["segment"] for p in r["profiles"])),
            "neutral_controls": [p["id"] for p in r["profiles"] if p["role"] == "neutral"],
            "model_configuration_count": len(r["models"]), "missing_relevant_perspectives": gaps,
            "starting_heuristic": {"narrow_segment": "Consider 2–3 relevant configurations initially.",
                                   "new_demo": "Consider 3–4 core preference configurations plus a neutral control initially.",
                                   "custom": "Use the smallest set relevant to the round questions."}[r["starting_point"]],
            "caution": "Adjustable planning heuristic, never a scientific sample size or human-population estimate.",
            "budget": r["budget"], "execution_started": False}


def validate_report(r, report):
    obj(report, ("schema_version", "id", "round_sha256", "profile_id", "model_id", "mode", "entry_point",
                 "context_id", "fresh_context", "prior_exposure", "repeat_index", "start_state_sha256",
                 "prompt_sha256", "seed", "fidelity", "audit_refs", "evidence", "choices",
                 "interpretations", "findings", "counterexamples", "end", "usage"), "report")
    require(type(report["schema_version"]) is int and report["schema_version"] == VERSION,
            "report: unsupported schema_version")
    ident(report["id"], "report.id")
    require(report["round_sha256"] == digest(r), "report: stale or wrong round identity")
    profiles = {p["id"]: p for p in r["profiles"]}
    require(report["profile_id"] in profiles, "report: unknown profile")
    require(report["model_id"] in {m["id"] for m in r["models"]}, "report: unknown model configuration")
    enum(report["mode"], MODES, "report.mode")
    for key in ("entry_point", "context_id", "seed"):
        string(report[key], "report." + key)
    require(type(report["fresh_context"]) is bool, "fresh_context: expected boolean")
    enum(report["prior_exposure"], ("none", "known", "unknown"), "prior_exposure")
    number(report["repeat_index"], "repeat_index", integer=True, minimum=1)
    for key in ("start_state_sha256", "prompt_sha256"):
        if report[key] is not None:
            sha(report[key], key)
    obj(report["fidelity"], FIDELITY, "fidelity")
    for key, flag in report["fidelity"].items():
        require(type(flag) is bool or flag is None, f"fidelity.{key}: expected boolean or null")
    strings(report["audit_refs"], "audit_refs")
    evidence = indexed(report["evidence"], "evidence", nonempty=False)
    scenarios = {s["id"] for s in r["scenarios"]}
    for item in evidence.values():
        obj(item, ("id", "scenario_id", "location", "source_ref", "source_sha256", "observation_seq",
                   "feedback_seq", "outcome_seq", "visible_observation", "action", "feedback"), "evidence")
        require(item["scenario_id"] in scenarios, "evidence: unknown scenario")
        for key in ("location", "source_ref", "visible_observation", "action", "feedback"):
            string(item[key], "evidence." + key)
        sha(item["source_sha256"], "evidence.source_sha256")
        for key in ("observation_seq", "feedback_seq"):
            number(item[key], "evidence." + key, integer=True)
        require(item["observation_seq"] < item["feedback_seq"], "feedback must follow observation")
        if item["outcome_seq"] is not None:
            number(item["outcome_seq"], "evidence.outcome_seq", integer=True)
            require(item["feedback_seq"] < item["outcome_seq"], "feedback must precede revealed outcome")
    def refs(value):
        strings(value, "evidence_ids", evidence, True)
    for choice in array(report["choices"], "choices"):
        obj(choice, ("location", "option_id", "evidence_ids"), "choice")
        string(choice["location"], "choice.location")
        string(choice["option_id"], "choice.option_id")
        refs(choice["evidence_ids"])
    for item in array(report["interpretations"], "interpretations"):
        obj(item, ("location", "meaning", "evidence_ids"), "interpretation")
        string(item["location"], "interpretation.location")
        string(item["meaning"], "interpretation.meaning")
        refs(item["evidence_ids"])
    for item in array(report["counterexamples"], "counterexamples"):
        obj(item, ("claim", "observation", "evidence_ids"), "counterexample")
        string(item["claim"], "counterexample.claim")
        string(item["observation"], "counterexample.observation")
        refs(item["evidence_ids"])
    for finding in indexed(report["findings"], "findings", nonempty=False).values():
        obj(finding, ("id", "location", "behavior", "consequence", "kind", "severity",
                      "contract_ref", "evidence_ids"), "finding")
        for key in ("location", "behavior", "consequence"):
            string(finding[key], "finding." + key)
        enum(finding["kind"], ("contract_defect", "suspected_issue", "preference"), "finding.kind")
        enum(finding["severity"], ("critical", "major", "minor"), "finding.severity")
        if finding["contract_ref"] is not None:
            string(finding["contract_ref"], "finding.contract_ref")
        require(finding["kind"] != "contract_defect" or finding["contract_ref"] is not None,
                "a contract defect requires an authored contract reference")
        require(finding["kind"] != "preference" or finding["severity"] != "critical",
                "a preference cannot be a critical blocker")
        refs(finding["evidence_ids"])
    obj(report["end"], ("reason", "detail", "evidence_ids"), "end")
    enum(report["end"]["reason"], ("terminal_screen", "player_quit", "resource_limit", "harness_failure", "blocked"), "end.reason")
    string(report["end"]["detail"], "end.detail")
    strings(report["end"]["evidence_ids"], "end.evidence_ids", evidence,
            report["end"]["reason"] in ("player_quit", "terminal_screen", "blocked"))
    obj(report["usage"], ("minutes", "turns", "model_calls", "tokens", "cost", "currency"), "usage")
    number(report["usage"]["turns"], "usage.turns", integer=True)
    for key in ("minutes", "model_calls"):
        if report["usage"][key] is not None:
            number(report["usage"][key], "usage." + key, integer=key != "minutes")
    for key in ("tokens", "cost"):
        if report["usage"][key] is not None:
            number(report["usage"][key], "usage." + key, integer=key == "tokens")
    currency = report["usage"]["currency"]
    require((report["usage"]["cost"] is None) == (currency is None), "cost and currency must both be known or null")
    if currency is not None:
        string(currency, "usage.currency")
    return report


def ingest(round_record, reports):
    r = validate_round(round_record)
    require(type(reports) is list and len(reports) <= MAX_REPORTS, "too many reports")
    total_bytes = 0
    for report in array(reports, "reports"):
        validate_report(r, report)
        total_bytes += len(json.dumps(report, ensure_ascii=False, allow_nan=False).encode())
        require(total_bytes <= MAX_REPORT_BYTES, "aggregate reports exceed byte limit")
    unique([x["id"] for x in reports], "session ids")
    # Duplicate contexts are retained but never treated as independent repeats.
    unique([(x["profile_id"], x["model_id"], x["mode"], x["entry_point"], x["prompt_sha256"], x["start_state_sha256"], x["repeat_index"])
            for x in reports], "profile/model/mode/entry repeat indices")
    return {"schema_version": VERSION, "round_sha256": digest(r),
            "report_sha256s": {x["id"]: digest(x) for x in reports}, "reports": reports}


def eligible(report):
    return (report["fresh_context"] and report["prior_exposure"] == "none"
            and all(report["fidelity"][key] is True for key in FIDELITY)
            and bool(report["audit_refs"]) and report["start_state_sha256"] is not None
            and report["prompt_sha256"] is not None)


def issue_key(finding):
    # Semantic equivalence remains a reviewer decision; exact normalized triples only.
    return digest([" ".join(finding[key].casefold().split())
                   for key in ("location", "behavior", "consequence")])


def features(reports):
    out = set()
    for r in reports:
        for c in r["choices"]:
            out.add(("choice", c["location"], c["option_id"]))
        for i in r["findings"]:
            out.add(("issue", issue_key(i)))
        for i in r["interpretations"]:
            out.add(("interpretation", i["location"], i["meaning"]))
        for i in r["counterexamples"]:
            out.add(("counterexample", i["claim"], i["observation"]))
    return out


def recommend(round_record, bundle, review=None):
    r = validate_round(round_record)
    obj(bundle, ("schema_version", "round_sha256", "report_sha256s", "reports"), "bundle")
    require(type(bundle["schema_version"]) is int and bundle["schema_version"] == VERSION,
            "bundle: unsupported schema_version")
    checked = ingest(r, bundle["reports"])
    require(bundle == checked, "bundle identity or report hashes do not match")
    reports = bundle["reports"]
    sessions = {x["id"]: x for x in reports}
    profiles = {x["id"]: x for x in r["profiles"]}
    questions = {x["id"]: x for x in r["questions"]}
    valid = [x for x in reports if eligible(x)]
    refs = {(s["id"], e["id"]): (s, e) for s in reports for e in s["evidence"]}
    def evidence_refs(value):
        result = []
        for ref in array(value, "review.evidence_refs", True):
            obj(ref, ("session_id", "evidence_id"), "review evidence reference")
            pair = (ref["session_id"], ref["evidence_id"])
            require(pair in refs, "review: unknown evidence reference")
            require(eligible(refs[pair][0]), "review: evidence lacks declared fidelity/provenance")
            result.append(refs[pair])
        unique([(s["id"], e["id"]) for s, e in result], "review evidence references")
        return result
    assessments, signals = {}, []
    if review is not None:
        obj(review, ("schema_version", "round_sha256", "bundle_sha256", "reviewer", "questions", "signals"), "review")
        require(type(review["schema_version"]) is int and review["schema_version"] == VERSION,
                "review: unsupported schema_version")
        require(review["round_sha256"] == digest(r), "review: wrong round identity")
        require(review["bundle_sha256"] == digest(checked), "review: stale or wrong bundle identity; reassess changed or appended records")
        string(review["reviewer"], "review.reviewer")
        assessments = indexed(review["questions"], "review.questions", nonempty=False)
        for item in assessments.values():
            obj(item, ("id", "ready", "answer", "decision", "evidence_refs"), "question assessment")
            require(item["id"] in questions, "review: unknown question")
            require(type(item["ready"]) is bool, "review.ready: expected boolean")
            string(item["answer"], "review.answer")
            string(item["decision"], "review.decision")
            cited = evidence_refs(item["evidence_refs"])
            q = questions[item["id"]]
            require(all(profiles[s["profile_id"]]["segment"] in q["segments"]
                        and s["mode"] in q["modes"] and e["scenario_id"] in q["scenarios"]
                        for s, e in cited), "question assessment cites out-of-scope evidence")
        signals = array(review["signals"], "review.signals")
        for signal in signals:
            obj(signal, ("kind", "profile_id", "compared_with", "rationale", "evidence_refs"), "signal")
            enum(signal["kind"], ("unstable", "shared_bias", "redundant"), "signal.kind")
            require(signal["profile_id"] in profiles, "signal: unknown profile")
            strings(signal["compared_with"], "signal.compared_with", profiles)
            require(signal["profile_id"] not in signal["compared_with"], "signal: cannot compare profile to itself")
            string(signal["rationale"], "signal.rationale")
            cited = evidence_refs(signal["evidence_refs"])
            require(any(s["profile_id"] == signal["profile_id"] for s, _ in cited), "signal must cite its profile")
    recommendations = []
    def add(action, reason, **details):
        recommendations.append({"action": action, "reason": reason, **details})
    for x in reports:
        if not eligible(x):
            add("inspect_record_or_harness", "Blind/engine/provenance declarations are incomplete; evidence excluded from decision readiness.", session_id=x["id"])
        if x["usage"]["minutes"] is None:
            add("inspect_usage", "Session duration is unknown; aggregate time consumption is a lower bound.", session_id=x["id"])
        if ((x["usage"]["minutes"] is not None and x["usage"]["minutes"] > r["budget"]["max_session_minutes"])
                or x["usage"]["turns"] > r["budget"]["max_turns"]):
            add("inspect_budget_overrun", "The adapter exceeded a per-session ceiling; do not reinterpret it as voluntary quitting.", session_id=x["id"])
    for gap in plan(r)["missing_relevant_perspectives"]:
        add("add_profile", "An audience-relevant preference is not represented in the plan.", **gap)
    for p in r["profiles"]:
        if p["segment"] == "core" and not any(x["profile_id"] == p["id"] for x in valid):
            add("run_planned_profile", "No eligible record for this planned core configuration.", profile_id=p["id"])
    coverage = {mode: {seg: sorted({e["scenario_id"] for s in valid if s["mode"] == mode
                                  and profiles[s["profile_id"]]["segment"] == seg for e in s["evidence"]})
                       for seg in SEGMENTS} for mode in MODES}
    question_results = []
    for q in r["questions"]:
        a = assessments.get(q["id"])
        cited = evidence_refs(a["evidence_refs"]) if a else []
        needed = {(sc, mo, sg) for sc in q["scenarios"] for mo in q["modes"] for sg in q["segments"]}
        observed = {(e["scenario_id"], s["mode"], profiles[s["profile_id"]]["segment"])
                    for s in valid for e in s["evidence"]}
        supported = {(e["scenario_id"], s["mode"], profiles[s["profile_id"]]["segment"]) for s, e in cited}
        gaps = [{"scenario_id": sc, "mode": mo, "segment": sg} for sc, mo, sg in sorted(needed - observed)]
        ready = bool(a and a["ready"] and needed <= supported)
        question_results.append({"id": q["id"], "ready": ready, "coverage_gaps": gaps,
                                 "assessment": a, "cited_coverage_sufficient": needed <= supported})
        for gap in gaps:
            add("targeted_gap_check", "A focused route can investigate this gap; targeted/chapter evidence never fills a natural-play requirement.", question_id=q["id"], **gap)
        if not ready and not gaps:
            add("review_question", "Coverage is not an answer; an explicit evidence-linked judgment is still needed.", question_id=q["id"])
    issues = {}
    for s in reports:
        for f in s["findings"]:
            key = issue_key(f)
            issue = issues.setdefault(key, {"key": key, "location": f["location"], "behavior": f["behavior"],
                                            "consequence": f["consequence"], "occurrences": []})
            issue["occurrences"].append({"session_id": s["id"], "finding_id": f["id"],
                                         "segment": profiles[s["profile_id"]]["segment"], "mode": s["mode"],
                                         "severity": f["severity"], "kind": f["kind"], "evidence_ids": f["evidence_ids"]})
    blockers = []
    for issue in issues.values():
        critical = [o for o in issue["occurrences"] if o["severity"] == "critical" and o["segment"] == "core"
                    and eligible(sessions[o["session_id"]])]
        contexts = {sessions[o["session_id"]]["context_id"] for o in critical}
        if len(contexts) >= 2:
            blockers.append(issue["key"])
            add("fix_shared_blocker", "A critical obstacle has evidence in distinct core contexts; stop sampling and review/fix it before replay.", issue_key=issue["key"])
        elif critical:
            add("repeat_profile", "A one-context critical finding needs a fresh independent repeat, not another persona vote.",
                profile_id=sessions[critical[0]["session_id"]]["profile_id"], issue_key=issue["key"])
    for signal in signals:
        p = signal["profile_id"]
        if signal["kind"] == "unstable":
            add("repeat_profile", signal["rationale"], profile_id=p, evidence_refs=signal["evidence_refs"])
        elif signal["kind"] == "shared_bias":
            add("crosscheck_model", signal["rationale"], profile_id=p, evidence_refs=signal["evidence_refs"])
        else:
            own = [s for s in valid if s["profile_id"] == p]
            others = [s for s in valid if s["profile_id"] in signal["compared_with"]
                      and profiles[s["profile_id"]]["segment"] == profiles[p]["segment"]
                      and profiles[s["profile_id"]]["role"] == profiles[p]["role"]]
            def context(s):
                return (s["mode"], s["entry_point"], s["model_id"], s["start_state_sha256"])
            own_contexts = {context(s) for s in own}
            other_contexts = {context(s) for s in others}
            comparable = bool(own and others and own_contexts <= other_contexts and features(own))
            no_novelty = comparable and all(
                features([s for s in own if context(s) == c]) <= features([s for s in others if context(s) == c])
                for c in own_contexts)
            add("consider_reducing_profile" if no_novelty else "retain_profile",
                "Reviewer-reported redundancy with no new recorded choice/problem/interpretation/counterexample in comparable contexts. Semantic equivalence still needs review."
                if no_novelty else "Redundancy is not supported by comparable recorded features.", profile_id=p,
                evidence_refs=signal["evidence_refs"])
    groups = defaultdict(list)
    for s in valid:
        groups[(s["profile_id"], s["model_id"], s["mode"], s["entry_point"], s["prompt_sha256"], s["start_state_sha256"])].append(s)
    repetitions = [{"profile_id": k[0], "model_id": k[1], "mode": k[2], "entry_point": k[3],
                    "prompt_sha256": k[4], "start_state_sha256": k[5],
                    "records": len(v), "distinct_contexts": len({s["context_id"] for s in v}),
                    "additional_independent_contexts": max(0, len({s["context_id"] for s in v}) - 1)}
                   for k, v in sorted(groups.items())]
    minutes = sum(s["usage"]["minutes"] for s in reports if s["usage"]["minutes"] is not None)
    exhausted = len(reports) >= r["budget"]["max_sessions"] or minutes >= r["budget"]["max_total_minutes"]
    ready = all(q["ready"] for q in question_results)
    status = "stop_fix_blocker" if blockers else "stop_decision_ready" if ready else "stop_budget_with_gaps" if exhausted else "continue_or_review"
    return {"schema_version": VERSION, "experimental": True, "round_sha256": digest(r),
            "status": status, "recommendations_are_advisory": True,
            "counts": {"planned_profiles": len(profiles), "observed_profiles": len({s["profile_id"] for s in reports}),
                       "sessions": len(reports), "eligible_records": len(valid),
                       "model_configurations": len({s["model_id"] for s in reports}),
                       "underlying_models": len({m["model"] for m in r["models"] if any(s["model_id"] == m["id"] for s in reports)}),
                       "known_minutes": minutes, "unknown_duration_sessions": sum(s["usage"]["minutes"] is None for s in reports)}, "repetitions": repetitions,
            "end_reasons": dict(Counter(s["end"]["reason"] for s in reports)),
            "coverage": coverage,
            "unobserved_scenarios": {mode: {seg: sorted({x["id"] for x in r["scenarios"]} - set(coverage[mode][seg]))
                                            for seg in SEGMENTS} for mode in MODES},
            "recorded_coverage_including_ineligible": {mode: {seg: sorted({e["scenario_id"] for s in reports if s["mode"] == mode
                and profiles[s["profile_id"]]["segment"] == seg for e in s["evidence"]}) for seg in SEGMENTS} for mode in MODES},
            "questions": question_results, "issues": list(issues.values()),
            "budget_exhausted": exhausted, "recommendations": recommendations,
            "limits": ["Caller-declared evidence and hashes are not authenticated engine or isolation proof.",
                       "Virtual configurations and independent contexts are not independent human participants.",
                       "No majority vote, prevalence estimate, statistical sample size, or human-quality certification.",
                       "Text/choice records do not establish rendered UI, physical controls, discoverability, or audio quality.",
                       "Coverage remains separated by mode and audience segment; all unobserved scope remains unclaimed."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Experimental offline audience-first playtest planning and evidence triage")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "ingest", "recommend"):
        p = sub.add_parser(name)
        p.add_argument("--round", required=True, dest="round_path")
        if name == "ingest":
            p.add_argument("--reports", nargs="+", required=True)
        elif name == "recommend":
            p.add_argument("--bundle", required=True)
            p.add_argument("--review")
    args = parser.parse_args(argv)
    try:
        r = load(args.round_path)
        if args.command == "plan":
            result = plan(r)
        elif args.command == "ingest":
            require(len(args.reports) <= MAX_REPORTS, "too many report files")
            reports, total_bytes = [], 0
            for path in args.reports:
                report = load(path)
                total_bytes += len(json.dumps(report, ensure_ascii=False, allow_nan=False).encode())
                require(total_bytes <= MAX_REPORT_BYTES, "aggregate reports exceed byte limit")
                reports.append(report)
            result = ingest(r, reports)
        else:
            result = recommend(r, load(args.bundle), load(args.review) if args.review else None)
        output = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        require(len(output.encode("utf-8")) + 1 <= MAX_OUTPUT_BYTES, "output exceeds byte limit; split the round")
        print(output)
        return 0
    except (ContractError, OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        print("playtesting: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
