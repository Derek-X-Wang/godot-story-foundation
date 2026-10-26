#!/usr/bin/env python3
"""Synthetic local fixtures only. No fixture is a story or listening decision."""
import array
import contextlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave

import audio_audit as audit


def write_wav(path, values, channels=1, rate=8000):
    pcm = array.array("h", [max(-32768, min(32767, round(v * 32768))) for v in values])
    if sys.byteorder != "little":
        pcm.byteswap()
    with wave.open(str(path), "wb") as output:
        output.setparams((channels, 2, rate, 0, "NONE", "not compressed"))
        output.writeframes(pcm.tobytes())


class Measurements(unittest.TestCase):
    def test_known_peak_rms_and_channel_dc_not_cancelled(self):
        samples = array.array("f", [.25, -.25] * 8000)
        metrics, loop = audit.measure_samples(samples, 2, 8000, audit.DEFAULT_POLICY, False)
        self.assertAlmostEqual(metrics["sample_peak_dbfs"], -12.0412, places=4)
        self.assertAlmostEqual(metrics["rms_dbfs"], -12.0412, places=4)
        self.assertEqual(metrics["max_abs_dc_offset"], .25)
        self.assertEqual(metrics["silence_intervals"], [])
        self.assertEqual(loop["status"], "not_requested")

    def test_silence_boundaries_and_zero_db_json_null(self):
        values = [0.] * 1600 + [.1, -.1] * 1600 + [0.] * 2400
        m, _ = audit.measure_samples(array.array("f", values), 1, 8000, audit.DEFAULT_POLICY, False)
        self.assertEqual([s["kind"] for s in m["silence_intervals"]], ["leading", "trailing"])
        self.assertAlmostEqual(m["silence_intervals"][0]["duration_s"], .2)
        self.assertAlmostEqual(m["silence_intervals"][1]["duration_s"], .3)
        silent, _ = audit.measure_samples(array.array("f", [0.] * 8000), 1, 8000, audit.DEFAULT_POLICY, False)
        self.assertIsNone(silent["rms_dbfs"])
        self.assertIsNone(silent["sample_peak_dbfs"])
        json.dumps(silent, allow_nan=False)

    def test_loop_discontinuity_flags_but_continuous_sine_does_not(self):
        jump = array.array("f", [.2] * 4000 + [-.2] * 4000)
        _, loop = audit.measure_samples(jump, 1, 8000, audit.DEFAULT_POLICY, True)
        self.assertEqual(loop["status"], "risk_flagged")
        self.assertIsNone(loop["channels"][0]["ratio_to_local_delta_rms"])
        tone = array.array("f", [.2 * math.sin(2 * math.pi * 250 * i / 8000) for i in range(8000)])
        _, loop = audit.measure_samples(tone, 1, 8000, audit.DEFAULT_POLICY, True)
        self.assertEqual(loop["status"], "no_risk_flagged")
        self.assertFalse(loop["perception_verified"])

    def test_invalid_samples_and_policy_rejected(self):
        for values in ([], [.1, float("nan")], [.1, float("inf")]):
            with self.assertRaises(ValueError):
                audit.measure_samples(array.array("f", values), 1, 8000, audit.DEFAULT_POLICY, False)
        for policy in ({"not_a_threshold": 1}, {"timeout_s": -1}, {"max_sample_peak_dbfs": float("nan")},
                       {"max_abs_dc_offset": True}, {"max_decoded_bytes": 100.5}):
            with self.assertRaises(ValueError):
                audit.policy_with(policy)
        self.assertEqual(audit.policy_with({"max_leading_silence_s": 0})["max_leading_silence_s"], 0)

    def test_over_full_scale_is_counted_per_channel(self):
        m, _ = audit.measure_samples(array.array("f", [1.1, -.1, .1, -1.2]), 2, 8000, audit.DEFAULT_POLICY, False)
        self.assertEqual(m["over_full_scale_samples"], 2)
        self.assertEqual(m["near_full_scale_samples"], 2)

    def test_extreme_finite_context_is_bounded_by_actual_audio(self):
        policy = audit.policy_with({"loop_context_s": 1e308})
        _, loop = audit.measure_samples(array.array("f", [.2, -.2] * 80), 1, 8000, policy, True)
        self.assertIn(loop["status"], ("risk_flagged", "no_risk_flagged"))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe required for decode integration fixtures")
class DecodeAndCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="audio-audit-tests-")
        self.root = Path(self.temp.name)
        self.tone = self.root / "tone.wav"
        write_wav(self.tone, [.2 * math.sin(2 * math.pi * 250 * i / 8000) for i in range(8000)])

    def tearDown(self):
        self.temp.cleanup()

    def inspect(self, path="tone.wav", **kwargs):
        return audit.audit_asset({"path": path, **kwargs}, self.root, audit.DEFAULT_POLICY)

    def test_valid_pcm_is_pass_not_perceptual_approval_and_input_unchanged(self):
        before = audit.file_sha256(self.tone)
        result = self.inspect(loop=True, category="sfx")
        self.assertEqual(result["decode"]["status"], "passed")
        self.assertEqual(result["technical_status"], "pass")
        self.assertEqual(result["format"]["sample_rate_hz"], 8000)
        self.assertEqual(result["metrics"]["decoded_frames"], 8000)
        self.assertAlmostEqual(result["metrics"]["decoded_duration_s"], 1.)
        self.assertEqual(result["source_sha256"], before)
        self.assertEqual(audit.file_sha256(self.tone), before)
        self.assertEqual(result["listening_status"], "not_assessed")
        self.assertFalse(result["perception_verified"])
        self.assertIsNone(result["metrics"]["integrated_lufs"])

    def test_missing_corrupt_and_truncated_are_failed_not_partial_passes(self):
        (self.root / "bad.wav").write_bytes(b"not audio")
        (self.root / "truncated.wav").write_bytes(self.tone.read_bytes()[:-200])
        for path in ("missing.wav", "bad.wav", "truncated.wav"):
            with self.subTest(path=path):
                result = self.inspect(path)
                self.assertEqual(result["technical_status"], "fail", result)
                self.assertEqual(result["decode"]["status"], "failed")

    def test_flac_decodes_and_matches_pcm_measurements(self):
        flac = self.root / "tone.flac"
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(self.tone), str(flac)], check=True)
        result = self.inspect("tone.flac")
        original = self.inspect()
        self.assertEqual(result["technical_status"], "pass")
        self.assertEqual(result["format"]["codec"], "flac")
        self.assertEqual(result["metrics"]["sample_peak_linear"], original["metrics"]["sample_peak_linear"])
        self.assertEqual(result["metrics"]["decoded_frames"], original["metrics"]["decoded_frames"])

    def test_full_scale_dc_and_silence_warn_with_stable_codes(self):
        write_wav(self.root / "clip.wav", [1., -1.] * 4000)
        result = self.inspect("clip.wav")
        self.assertEqual(result["technical_status"], "warn")
        self.assertIn("near_full_scale", [f["code"] for f in result["findings"]])
        write_wav(self.root / "dc.wav", [.1] * 8000)
        self.assertIn("dc_offset", [f["code"] for f in self.inspect("dc.wav")["findings"]])
        write_wav(self.root / "silence.wav", [0.] * 8000)
        self.assertIn("silence_full_file", [f["code"] for f in self.inspect("silence.wav")["findings"]])

    def test_short_sfx_does_not_get_lufs_gate(self):
        write_wav(self.root / "short.wav", [.2, -.2] * 80)
        result = self.inspect("short.wav", category="sfx")
        self.assertEqual(result["technical_status"], "pass")
        self.assertEqual(result["metrics"]["loudness_status"], "not_measured")

    def test_configured_size_limit_fails_without_partial_metrics(self):
        result = self.inspect(policy={"max_decoded_bytes": 100})
        self.assertEqual(result["technical_status"], "fail")
        self.assertEqual(result["metrics"], {})

    def test_manifest_policy_override_and_report_contract(self):
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps({"assets": [{"id": "fixture", "path": "tone.wav", "loop": True}],
                                        "policy": {"max_sample_peak_dbfs": -30}}))
        output = self.root / "report.json"
        args = ["--manifest", str(manifest), "--base-dir", str(self.root), "--output", str(output)]
        self.assertEqual(audit.main(args), 0)
        self.assertEqual(audit.main(args + ["--fail-on-warning"]), 1)
        report = json.loads(output.read_text())
        schema = json.loads(Path(__file__).with_name("audio_audit.schema.json").read_text())
        self.assertTrue(set(schema["required"]).issubset(report))
        self.assertTrue(set(schema["$defs"]["asset"]["required"]).issubset(report["assets"][0]))
        self.assertEqual(report["schema_version"], "audio-technical-report.v1")
        self.assertEqual(report["summary"], {"assets": 1, "pass": 0, "warn": 1, "fail": 0})
        self.assertEqual(report["assets"][0]["id"], "fixture")
        self.assertFalse(report["perception_verified"])
        self.assertIn("not a universal", report["policy_basis"])

    def test_output_cannot_overwrite_input_and_duplicate_ids_rejected(self):
        before = self.tone.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            code = audit.main([str(self.tone), "--output", str(self.tone)])
        self.assertEqual(code, 2)
        self.assertEqual(self.tone.read_bytes(), before)
        linked = self.root / "hardlink.wav"
        os.link(self.tone, linked)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(audit.main([str(self.tone), "--output", str(linked)]), 2)
        self.assertEqual(self.tone.read_bytes(), before)
        with self.assertRaises(ValueError):
            audit.validate_specs([{"path": "a", "id": "same"}, {"path": "b", "id": "same"}])

    def test_asset_policy_overrides_global_policy(self):
        report = audit.build_report([{"path": "tone.wav", "policy": {"max_sample_peak_dbfs": -1}}],
                                    self.root, {"max_sample_peak_dbfs": -30})
        self.assertEqual(report["assets"][0]["technical_status"], "pass")

    def test_float_wav_over_full_scale_fails(self):
        raw = self.root / "over.f32le"
        values = array.array("f", [1.1, -1.2] * 800)
        if sys.byteorder != "little":
            values.byteswap()
        raw.write_bytes(values.tobytes())
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "f32le", "-ar", "8000", "-ac", "1",
                        "-i", str(raw), "-c:a", "pcm_f32le", str(self.root / "over.wav")], check=True)
        result = self.inspect("over.wav")
        self.assertEqual(result["decode"]["status"], "passed")
        self.assertEqual(result["technical_status"], "fail")
        self.assertEqual(result["metrics"]["over_full_scale_samples"], 1600)
        self.assertIn("over_full_scale", [f["code"] for f in result["findings"]])

    def test_extreme_finite_policy_is_friendly_exit_two_without_report(self):
        for policy in ({"silence_threshold_dbfs": 1e308}, {"silence_threshold_dbfs": -1e308},
                       {"loop_boundary_jump_dbfs": 1e308}, {"timeout_s": 1e308}):
            with self.subTest(policy=policy):
                config = self.root / "policy.json"
                config.write_text(json.dumps(policy))
                output = self.root / "should-not-exist.json"
                error = io.StringIO()
                with contextlib.redirect_stderr(error):
                    result = audit.main([str(self.tone), "--policy", str(config), "--output", str(output)])
                self.assertEqual(result, 2)
                self.assertFalse(output.exists())
                self.assertIn("audio_audit:", error.getvalue())
                self.assertNotIn("Traceback", error.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
