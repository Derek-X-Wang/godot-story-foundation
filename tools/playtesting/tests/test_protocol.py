"""Neutral offline regressions; no model/game execution or private material."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("playtest_protocol", ROOT / "protocol.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.r = p.load(ROOT / "examples/round.json")
        self.s = p.load(ROOT / "examples/session.json")
        self.review = p.load(ROOT / "examples/review.json")

    def bind(self, *reports):
        for s in reports:
            s["round_sha256"] = p.digest(self.r)
        self.review["round_sha256"] = p.digest(self.r)

    def result(self, reports=None, review=None):
        bundle = p.ingest(self.r, reports or [self.s])
        if review is not None:
            # These synthetic tests review their varied inputs afresh. Stale-review
            # regressions below call the API directly without this helper.
            review = copy.deepcopy(review)
            review["bundle_sha256"] = p.digest(bundle)
        return p.recommend(self.r, bundle, review)

    def repeat(self, profile=None, context="fresh-context-2"):
        s = copy.deepcopy(self.s)
        s["id"] = "session-2"
        s["context_id"] = context
        if profile:
            s["profile_id"] = profile
        else:
            s["repeat_index"] = 2
        return s

    def finding(self, severity="critical", kind="suspected_issue"):
        return {"id": "f1", "location": "gate", "behavior": "Offered action fails",
                "consequence": "Cannot proceed", "kind": kind, "severity": severity,
                "contract_ref": None, "evidence_ids": ["e1"]}

    def signal(self, kind, compared=()):
        self.review["signals"] = [{"kind": kind, "profile_id": "curious",
            "compared_with": list(compared), "rationale": "Synthetic evidence-linked judgment.",
            "evidence_refs": [{"session_id": self.s["id"], "evidence_id": "e1"}]}]

    def test_plan_experimental_and_heuristic_not_execution(self):
        plan = p.plan(self.r)
        self.assertTrue(plan["experimental"])
        self.assertFalse(plan["execution_started"])
        self.assertEqual(plan["neutral_controls"], ["neutral"])
        self.assertIn("scientific", plan["caution"])

    def test_missing_audience_axis_adds_profile(self):
        self.r["axes"][0]["relevant_values"].append("immediate_consequences")
        self.bind(self.s)
        actions = self.result()["recommendations"]
        self.assertTrue(any(x["action"] == "add_profile" and x["value"] == "immediate_consequences" for x in actions))

    def test_non_target_does_not_fill_core_perspective(self):
        self.r["axes"][0]["relevant_values"].append("immediate_consequences")
        self.assertEqual(p.plan(self.r)["missing_relevant_perspectives"][0]["value"], "immediate_consequences")

    def test_invalid_round_fields_rejected(self):
        mutations = [lambda r: r.update(extra=1), lambda r: r.update(schema_version=True),
                     lambda r: r["budget"].update(max_sessions=True),
                     lambda r: r["budget"].update(max_total_minutes=float("nan")),
                     lambda r: r["profiles"][2]["preferences"].update(motivation="curiosity"),
                     lambda r: r["profiles"][0].update(preferences={}),
                     lambda r: r["questions"][0].update(scenarios=["missing"]),
                     lambda r: r["questions"][0].update(segments=["non_target"]),
                     lambda r: r["profiles"].append(copy.deepcopy(r["profiles"][0]))]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                r = copy.deepcopy(self.r)
                mutate(r)
                with self.assertRaises(p.ContractError):
                    p.validate_round(r)

    def test_stale_round_rejected(self):
        self.r["audience"]["core"] += " Updated."
        with self.assertRaisesRegex(p.ContractError, "wrong round"):
            p.ingest(self.r, [self.s])

    def test_inputs_not_mutated_and_output_deterministic(self):
        original = copy.deepcopy((self.r, self.s, self.review))
        first = self.result(review=self.review)
        self.assertEqual(first, self.result(review=self.review))
        self.assertEqual(original, (self.r, self.s, self.review))

    def test_feedback_after_outcome_rejected(self):
        self.s["evidence"][0]["feedback_seq"] = 2
        with self.assertRaisesRegex(p.ContractError, "precede"):
            p.ingest(self.r, [self.s])

    def test_feedback_before_observation_rejected(self):
        self.s["evidence"][0]["observation_seq"] = 2
        with self.assertRaisesRegex(p.ContractError, "follow"):
            p.ingest(self.r, [self.s])

    def test_unknown_evidence_rejected(self):
        self.s["choices"][0]["evidence_ids"] = ["missing"]
        with self.assertRaises(p.ContractError):
            p.ingest(self.r, [self.s])

    def test_missing_contract_cannot_be_confirmed_defect(self):
        self.s["findings"] = [self.finding(kind="contract_defect")]
        with self.assertRaisesRegex(p.ContractError, "authored contract"):
            p.ingest(self.r, [self.s])

    def test_critical_preference_rejected(self):
        self.s["findings"] = [self.finding(kind="preference")]
        with self.assertRaises(p.ContractError):
            p.ingest(self.r, [self.s])

    def test_resource_cutoff_never_counted_as_quitting(self):
        result = self.result()
        self.assertEqual(result["end_reasons"], {"resource_limit": 1})
        self.assertNotIn("completion_rate", result)

    def test_voluntary_stop_requires_evidence(self):
        self.s["end"]["reason"] = "player_quit"
        with self.assertRaises(p.ContractError):
            p.ingest(self.r, [self.s])
        self.s["end"]["evidence_ids"] = ["e1"]
        self.assertEqual(self.result()["end_reasons"], {"player_quit": 1})

    def test_budget_stop_preserves_gaps(self):
        self.r["budget"]["max_sessions"] = 1
        self.bind(self.s)
        result = self.result()
        self.assertEqual(result["status"], "stop_budget_with_gaps")
        self.assertTrue(result["questions"][1]["coverage_gaps"])

    def test_unknown_duration_is_not_zero_claim(self):
        self.s["usage"]["minutes"] = None
        self.s["usage"]["model_calls"] = None
        result = self.result()
        self.assertEqual(result["counts"]["unknown_duration_sessions"], 1)
        self.assertTrue(any(x["action"] == "inspect_usage" for x in result["recommendations"]))

    def test_per_session_overrun_is_diagnostic(self):
        self.s["usage"]["turns"] = 100
        self.assertTrue(any(x["action"] == "inspect_budget_overrun" for x in self.result()["recommendations"]))

    def test_coverage_does_not_answer_question(self):
        result = self.result()
        self.assertFalse(result["questions"][0]["ready"])
        self.assertTrue(any(x["action"] == "review_question" for x in result["recommendations"]))

    def test_explicit_supported_decision_can_stop_with_unclaimed_routes(self):
        self.r["questions"] = self.r["questions"][:1]
        self.bind(self.s)
        result = self.result(review=self.review)
        self.assertEqual(result["status"], "stop_decision_ready")
        self.assertIn("side_path", result["unobserved_scenarios"]["natural"]["core"])

    def test_targeted_cannot_fill_natural_gap(self):
        self.s["mode"] = "targeted"
        result = self.result()
        self.assertEqual(result["coverage"]["natural"]["core"], [])
        self.assertEqual(result["coverage"]["targeted"]["core"], ["entry"])
        self.assertTrue(result["questions"][0]["coverage_gaps"])
        with self.assertRaisesRegex(p.ContractError, "out-of-scope"):
            self.result(review=self.review)

    def test_chapter_coverage_is_separate(self):
        self.s["mode"] = "chapter"
        result = self.result()
        self.assertEqual(result["coverage"]["chapter"]["core"], ["entry"])
        self.assertEqual(result["coverage"]["natural"]["core"], [])

    def test_non_target_never_fills_core_question(self):
        self.s["profile_id"] = "diagnostic"
        result = self.result()
        self.assertEqual(result["coverage"]["natural"]["non_target"], ["entry"])
        self.assertTrue(result["questions"][0]["coverage_gaps"])
        with self.assertRaisesRegex(p.ContractError, "out-of-scope"):
            self.result(review=self.review)

    def test_degraded_records_retained_but_excluded(self):
        for flag in p.FIDELITY:
            s = copy.deepcopy(self.s)
            s["fidelity"][flag] = None
            result = self.result([s])
            self.assertEqual(result["counts"]["eligible_records"], 0)
            self.assertEqual(result["recorded_coverage_including_ineligible"]["natural"]["core"], ["entry"])

    def test_exposure_or_missing_provenance_excludes(self):
        for key, value in [("fresh_context", False), ("prior_exposure", "known"), ("prior_exposure", "unknown"),
                           ("audit_refs", []), ("prompt_sha256", None), ("start_state_sha256", None)]:
            s = copy.deepcopy(self.s)
            s[key] = value
            self.assertEqual(self.result([s])["counts"]["eligible_records"], 0)

    def test_degraded_evidence_cannot_be_reviewed_as_ready(self):
        self.s["prior_exposure"] = "known"
        with self.assertRaisesRegex(p.ContractError, "fidelity"):
            self.result(review=self.review)

    def test_bundle_tampering_rejected(self):
        b = p.ingest(self.r, [self.s])
        b["reports"][0]["evidence"][0]["feedback"] = "Altered"
        with self.assertRaisesRegex(p.ContractError, "hashes"):
            p.recommend(self.r, b)

    def test_stale_review_rejects_changed_cited_report(self):
        self.s["evidence"][0]["feedback"] = "An adverse new interpretation"
        self.s["evidence"][0]["source_sha256"] = "e" * 64
        with self.assertRaisesRegex(p.ContractError, "bundle identity"):
            p.recommend(self.r, p.ingest(self.r, [self.s]), self.review)

    def test_stale_review_rejects_appended_evidence(self):
        s = self.repeat()
        s["findings"] = [self.finding()]
        with self.assertRaisesRegex(p.ContractError, "bundle identity"):
            p.recommend(self.r, p.ingest(self.r, [self.s, s]), self.review)

    def test_changed_prompt_or_state_not_same_configuration_repeat(self):
        for key in ("prompt_sha256", "start_state_sha256"):
            s = self.repeat()
            s[key] = "f" * 64
            s["repeat_index"] = 1
            result = self.result([self.s, s])
            self.assertEqual(len(result["repetitions"]), 2)
            self.assertTrue(all(x["additional_independent_contexts"] == 0 for x in result["repetitions"]))

    def test_boolean_bundle_version_rejected(self):
        b = p.ingest(self.r, [self.s])
        b["schema_version"] = True
        with self.assertRaises(p.ContractError):
            p.recommend(self.r, b)

    def test_duplicate_sessions_and_repeat_indices_rejected(self):
        with self.assertRaises(p.ContractError):
            p.ingest(self.r, [self.s, self.s])
        s = self.repeat()
        s["repeat_index"] = 1
        with self.assertRaises(p.ContractError):
            p.ingest(self.r, [self.s, s])

    def test_same_context_does_not_create_independent_repeat(self):
        s = self.repeat(context=self.s["context_id"])
        result = self.result([self.s, s])
        self.assertEqual(result["repetitions"][0]["additional_independent_contexts"], 0)
        self.assertEqual(result["counts"]["sessions"], 2)

    def test_fresh_context_repeat_separate_from_profiles(self):
        result = self.result([self.s, self.repeat()])
        self.assertEqual(result["repetitions"][0]["additional_independent_contexts"], 1)
        self.assertEqual(result["counts"]["observed_profiles"], 1)

    def test_model_config_count_separate_from_underlying_model(self):
        m = copy.deepcopy(self.r["models"][0]); m["id"] = "offline-b"
        self.r["models"].append(m)
        s = self.repeat(); s["model_id"] = "offline-b"; s["repeat_index"] = 1
        self.bind(self.s, s)
        result = self.result([self.s, s])
        self.assertEqual(result["counts"]["model_configurations"], 2)
        self.assertEqual(result["counts"]["underlying_models"], 1)

    def test_one_off_critical_recommends_repeat(self):
        self.s["findings"] = [self.finding()]
        result = self.result()
        self.assertTrue(any(x["action"] == "repeat_profile" for x in result["recommendations"]))
        self.assertNotEqual(result["status"], "stop_fix_blocker")

    def test_dedup_issues_not_votes_and_shared_blocker(self):
        self.s["findings"] = [self.finding()]
        s = self.repeat(profile="relational")
        s["findings"][0]["behavior"] = "  offered ACTION fails "
        result = self.result([self.s, s])
        self.assertEqual(len(result["issues"]), 1)
        self.assertEqual(result["status"], "stop_fix_blocker")

    def test_same_context_does_not_corroborate_critical(self):
        self.s["findings"] = [self.finding()]
        result = self.result([self.s, self.repeat(context=self.s["context_id"])])
        self.assertNotEqual(result["status"], "stop_fix_blocker")

    def test_non_target_critical_not_shared_core_blocker(self):
        self.s["findings"] = [self.finding()]
        result = self.result([self.s, self.repeat(profile="diagnostic")])
        self.assertNotEqual(result["status"], "stop_fix_blocker")

    def test_unstable_and_shared_bias_need_evidence(self):
        for kind, action in [("unstable", "repeat_profile"), ("shared_bias", "crosscheck_model")]:
            self.signal(kind)
            self.assertTrue(any(x["action"] == action for x in self.result(review=self.review)["recommendations"]))
        self.review["signals"][0]["evidence_refs"] = []
        with self.assertRaises(p.ContractError):
            self.result(review=self.review)

    def test_redundancy_is_conditional(self):
        s = self.repeat(profile="relational")
        self.signal("redundant", ["relational"])
        result = self.result([self.s, s], self.review)
        self.assertTrue(any(x["action"] == "consider_reducing_profile" for x in result["recommendations"]))
        self.s["counterexamples"] = [{"claim": "Every sign is clear", "observation": "One symbol has no explanation", "evidence_ids": ["e1"]}]
        result = self.result([self.s, s], self.review)
        self.assertTrue(any(x["action"] == "retain_profile" for x in result["recommendations"]))

    def test_neutral_is_not_reduced_against_motivated(self):
        s = self.repeat(profile="neutral")
        self.signal("redundant", ["neutral"])
        self.assertTrue(any(x["action"] == "retain_profile" for x in self.result([self.s, s], self.review)["recommendations"]))

    def test_empty_records_do_not_prove_redundancy(self):
        s = self.repeat(profile="relational")
        self.s["choices"] = self.s["interpretations"] = []
        s["choices"] = s["interpretations"] = []
        self.signal("redundant", ["relational"])
        self.assertTrue(any(x["action"] == "retain_profile" for x in self.result([self.s, s], self.review)["recommendations"]))

    def test_duplicate_json_keys_and_nonfinite_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "bad.json"
            for content in ['{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}']:
                f.write_text(content)
                with self.assertRaises(p.ContractError):
                    p.load(f)

    def test_extreme_integer_rejected_without_overflow(self):
        self.r["budget"]["max_sessions"] = 10 ** 400
        with self.assertRaises(p.ContractError):
            p.validate_round(self.r)

    def test_text_and_report_count_bounded(self):
        self.s["evidence"][0]["feedback"] = "x" * (p.MAX_TEXT + 1)
        with self.assertRaises(p.ContractError):
            p.ingest(self.r, [self.s])
        with self.assertRaises(p.ContractError):
            p.ingest(self.r, [self.s] * (p.MAX_REPORTS + 1))

    def test_input_bytes_arrays_nesting_and_nonregular_bounded(self):
        import os
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "input.json"
            for content in [" " * (p.MAX_DOCUMENT_BYTES + 1),
                            json.dumps([0] * (p.MAX_ITEMS + 1)),
                            "[" * 34 + "0" + "]" * 34]:
                f.write_text(content)
                with self.assertRaises(p.ContractError):
                    p.load(f)
            if hasattr(os, "mkfifo"):
                fifo = Path(d) / "pipe"
                os.mkfifo(fifo)
                with self.assertRaises(p.ContractError):
                    p.load(fifo)

    def test_cli_huge_numeric_and_output_limit_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "round.json"
            self.r["budget"]["max_sessions"] = 10 ** 400
            f.write_text(json.dumps(self.r))
            cp = subprocess.run([sys.executable, str(ROOT / "protocol.py"), "plan", "--round", str(f)], capture_output=True, text=True)
            self.assertEqual(cp.returncode, 2)
            self.assertNotIn("Traceback", cp.stderr)
        import contextlib
        import io
        old = p.MAX_OUTPUT_BYTES
        p.MAX_OUTPUT_BYTES = 1
        try:
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(p.main(["plan", "--round", str(ROOT / "examples/round.json")]), 2)
            self.assertEqual(out.getvalue(), "")
        finally:
            p.MAX_OUTPUT_BYTES = old

    def test_standalone_cli_without_repository_imports(self):
        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / "protocol.py"
            shutil.copy(ROOT / "protocol.py", script)
            def run(*args):
                return subprocess.run([sys.executable, "-I", str(script), *map(str, args)], cwd=d, capture_output=True, text=True)
            planned = run("plan", "--round", ROOT / "examples/round.json")
            self.assertEqual(planned.returncode, 0, planned.stderr)
            ingested = run("ingest", "--round", ROOT / "examples/round.json", "--reports", ROOT / "examples/session.json")
            self.assertEqual(ingested.returncode, 0, ingested.stderr)
            bundle = Path(d) / "bundle.json"; bundle.write_text(ingested.stdout)
            result = run("recommend", "--round", ROOT / "examples/round.json", "--bundle", bundle, "--review", ROOT / "examples/review.json")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "continue_or_review")
            missing = run("plan", "--round", Path(d) / "absent.json")
            self.assertEqual(missing.returncode, 2)


if __name__ == "__main__":
    unittest.main()
