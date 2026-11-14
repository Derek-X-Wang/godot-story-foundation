"""Neutral, generated fixtures for the optional portrait idle manifest preflight."""
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
import importlib.util
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("portrait_idle_validate", ROOT / "tools/portrait_idle/validate.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def png(path, width=16, height=16):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    pixels = b"".join(b"\0" + b"\0\0\0\xff" * width for _ in range(height))
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


def sample():
    return {"schema_version": 1, "id": "neutral", "base": "base.png", "canvas": [16, 16], "pose": "full", "review_tier": "batch",
            "rig": {"backend": "mesh_v1", "grid_px": 4, "pin_y": [2, 12],
                    "breath": {"x_fade": [1, 3, 13, 15], "y_fade": [2, 4, 10, 12], "side": [8, 4], "displacement": [0.2, -0.2]},
                    "elbow": {"pivot": [11, 10], "angle_radians": -0.05, "x_fade": [9, 10, 13, 15], "y_fade": [4, 5, 11, 12]}},
            "eyes": {"mode": "static"}}


class IdleBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        png(self.root / "base.png")

    def test_mesh_ready_but_static_eyes_stay_in_queue(self):
        result = validator.validate(sample(), self.root)
        self.assertEqual(result["status"], "machine_ready")
        self.assertIn("eyes_static_no_blink_or_gaze", result["manual_queue"])

    def test_layered_eyes_require_registered_images(self):
        record = sample()
        record["eyes"] = {"mode": "layered", "region": [1, 1, 8, 4], "half": "half.png", "closed": "closed.png"}
        self.assertEqual(validator.validate(record, self.root)["status"], "invalid")
        png(self.root / "half.png")
        png(self.root / "closed.png")
        result = validator.validate(record, self.root)
        self.assertEqual(result["status"], "machine_ready")
        self.assertIn("eyelid_registration_review", result["manual_queue"])

    def test_external_adapter_is_never_claimed_assembled(self):
        record = sample()
        record["rig"] = {"backend": "external"}
        result = validator.validate(record, self.root)
        self.assertEqual(result["status"], "adapter_only")
        self.assertIn("external_rig_visual_and_motion_review", result["manual_queue"])

    def test_invalid_anchor_canvas_and_escape_fail_closed(self):
        record = sample()
        record["rig"]["pin_y"] = [12, 2]
        record["base"] = "../secret.png"
        record["canvas"] = [15, 16]
        result = validator.validate(record, self.root)
        self.assertEqual(result["status"], "invalid")
        self.assertGreaterEqual(len(result["errors"]), 3)

    def test_batch_reports_invalid_and_manual_separately(self):
        ready = self.root / "ready.json"
        ready.write_text(json.dumps(sample()))
        broken = self.root / "broken.json"
        broken.write_text("{")
        report = validator.batch([ready, broken], self.root)
        self.assertEqual(report["counts"], {"machine_ready": 1, "adapter_only": 0, "invalid": 1})
        self.assertEqual(len(report["manual_queue"]), 1)

    def test_forty_neutral_records_are_batched_without_visual_claim(self):
        paths = []
        for index in range(40):
            record = sample()
            record["id"] = f"neutral_{index:02d}"
            if index % 10 == 0:
                record["eyes"] = {"mode": "layered", "region": [1, 1, 8, 4], "half": "missing.png", "closed": "missing.png"}
            path = self.root / f"{index:02d}.json"
            path.write_text(json.dumps(record))
            paths.append(path)
        report = validator.batch(paths, self.root)
        self.assertEqual(report["counts"], {"machine_ready": 36, "adapter_only": 0, "invalid": 4})
        self.assertEqual(len(report["manual_queue"]), 40)

    def test_excessive_mesh_is_rejected(self):
        record = sample()
        record["canvas"] = [1024, 1024]
        record["rig"]["grid_px"] = 1
        self.assertEqual(validator.validate(record, self.root)["status"], "invalid")

    def test_side_anchor_outside_canvas_is_rejected(self):
        record = sample()
        record["rig"]["breath"]["side"] = [999, 4]
        self.assertEqual(validator.validate(record, self.root)["status"], "invalid")

    def test_duplicate_ids_and_keys_fail_closed(self):
        first = self.root / "one.json"
        second = self.root / "two.json"
        first.write_text(json.dumps(sample()))
        second.write_text(json.dumps(sample()))
        self.assertEqual(validator.batch([first, second], self.root)["counts"]["invalid"], 1)
        second.write_text('{"schema_version":1,"schema_version":1}')
        self.assertIn("duplicate JSON key", validator.batch([second], self.root)["records"][0]["errors"][0])


if __name__ == "__main__":
    unittest.main()
