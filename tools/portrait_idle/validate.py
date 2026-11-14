#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Derek Wang
"""Optional portrait idle asset/anchor preflight; visual approval remains separate."""
import argparse
import json
import math
import struct
from pathlib import Path


def nums(value, count):
    return isinstance(value, list) and len(value) == count and all(type(v) in (int, float) and math.isfinite(v) for v in value)


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError(f"non-finite JSON number: {value}")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject_constant)


def fade(value, name, limit, errors):
    if not nums(value, 4) or not value[0] < value[1] <= value[2] < value[3]:
        errors.append(f"{name}: four ascending fade coordinates required")
    elif value[0] < 0 or value[3] > limit:
        errors.append(f"{name}: fade must fit canvas")


def art(root, relative, canvas, name, errors):
    if not isinstance(relative, str) or not relative or relative.startswith("res://"):
        errors.append(f"{name}: project-relative PNG required")
        return
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path.suffix.lower() != ".png":
        errors.append(f"{name}: unsafe or non-PNG path")
        return
    try:
        with path.open("rb") as stream:
            header = stream.read(24)
    except OSError:
        errors.append(f"{name}: missing PNG")
        return
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        errors.append(f"{name}: invalid PNG header")
    elif list(struct.unpack(">II", header[16:24])) != canvas:
        errors.append(f"{name}: canvas mismatch")


def validate(record, root):
    errors, queue = [], []
    if not isinstance(record, dict) or record.get("schema_version") != 1:
        return {"status": "invalid", "errors": ["schema_version must be 1"], "manual_queue": []}
    ident = record.get("id")
    if not isinstance(ident, str) or not ident.strip():
        errors.append("id: nonempty string required")
    canvas = record.get("canvas")
    if not nums(canvas, 2) or any(type(v) is not int or v <= 0 for v in canvas):
        errors.append("canvas: positive integer pair required")
        canvas = [0, 0]
    art(root, record.get("base"), canvas, "base", errors)
    pose = record.get("pose")
    if pose not in ("full", "half"):
        errors.append("pose: full or half required")
    tier = record.get("review_tier")
    if tier not in ("batch", "main"):
        errors.append("review_tier: batch or main required")
    elif tier == "main":
        queue.append("main_cast_art_acceptance")
    rig = record.get("rig")
    if not isinstance(rig, dict):
        rig = {}
        errors.append("rig: object required")
    backend = rig.get("backend")
    if backend == "mesh_v1":
        grid = rig.get("grid_px")
        if type(grid) is not int or grid <= 0 or grid > 128 or canvas[0] % grid or canvas[1] % grid:
            errors.append("rig.grid_px: <=128 positive canvas divisor required")
        elif (canvas[0] // grid + 1) * (canvas[1] // grid + 1) > 65536:
            errors.append("rig.grid_px: mesh exceeds 65536 rest vertices")
        pin = rig.get("pin_y")
        if not nums(pin, 2) or not 0 <= pin[0] < pin[1] <= canvas[1]:
            errors.append("rig.pin_y: in-canvas bounds required")
        breath = rig.get("breath")
        if not isinstance(breath, dict):
            breath = {}
            errors.append("rig.breath: object required")
        fade(breath.get("x_fade"), "rig.breath.x_fade", canvas[0], errors)
        fade(breath.get("y_fade"), "rig.breath.y_fade", canvas[1], errors)
        if nums(pin, 2) and nums(breath.get("y_fade"), 4) and not pin[0] <= breath["y_fade"][0] < breath["y_fade"][3] <= pin[1]:
            errors.append("rig.breath.y_fade: must taper within unpinned band")
        side = breath.get("side")
        if not nums(breath.get("displacement"), 2) or not nums(side, 2) or side[1] <= 0:
            errors.append("rig.breath: displacement and [center, positive radius] required")
        elbow = rig.get("elbow")
        if elbow is not None:
            if not isinstance(elbow, dict):
                errors.append("rig.elbow: object required")
            else:
                if not nums(elbow.get("pivot"), 2) or not 0 <= elbow["pivot"][0] <= canvas[0] or not 0 <= elbow["pivot"][1] <= canvas[1]:
                    errors.append("rig.elbow.pivot: coordinate pair required")
                angle = elbow.get("angle_radians")
                if type(angle) not in (int, float) or not math.isfinite(angle) or abs(angle) > 0.25:
                    errors.append("rig.elbow.angle_radians: finite small angle required")
                fade(elbow.get("x_fade"), "rig.elbow.x_fade", canvas[0], errors)
                fade(elbow.get("y_fade"), "rig.elbow.y_fade", canvas[1], errors)
                if nums(pin, 2) and nums(elbow.get("y_fade"), 4) and not pin[0] <= elbow["y_fade"][0] < elbow["y_fade"][3] <= pin[1]:
                    errors.append("rig.elbow.y_fade: must taper within unpinned band")
        queue.append("motion_seam_and_pose_spotcheck")
    elif backend == "external":
        queue.append("external_rig_visual_and_motion_review")
    else:
        errors.append("rig.backend: mesh_v1 or external required")
    eyes = record.get("eyes")
    if not isinstance(eyes, dict) or eyes.get("mode") not in ("static", "layered"):
        errors.append("eyes.mode: static or layered required")
    elif eyes["mode"] == "layered":
        region = eyes.get("region")
        if not nums(region, 4) or region[2] <= 0 or region[3] <= 0 or region[0] < 0 or region[1] < 0 or region[0]+region[2] > canvas[0] or region[1]+region[3] > canvas[1]:
            errors.append("eyes.region: in-canvas rectangle required")
        for key in ("half", "closed"):
            art(root, eyes.get(key), canvas, "eyes."+key, errors)
        queue.append("eyelid_registration_review")
    else:
        queue.append("eyes_static_no_blink_or_gaze")
    return {"id": ident, "status": "invalid" if errors else ("machine_ready" if backend == "mesh_v1" else "adapter_only"), "errors": errors, "manual_queue": queue}


def batch(paths, root):
    records = []
    seen = set()
    for path in paths:
        try:
            result = validate(strict_json(Path(path).read_text(encoding="utf-8")), root)
        except (OSError, ValueError) as exc:
            result = {"status": "invalid", "errors": [str(exc)], "manual_queue": []}
        result["manifest"] = str(path)
        if result.get("id") in seen and result["status"] != "invalid":
            result["status"] = "invalid"
            result["errors"].append("duplicate pose id")
        if result.get("id") is not None:
            seen.add(result["id"])
        records.append(result)
    return {"schema_version": 1, "records": records, "counts": {s: sum(r["status"] == s for r in records) for s in ("machine_ready", "adapter_only", "invalid")}, "manual_queue": [{"id": r.get("id"), "manifest": r["manifest"], "reasons": r["manual_queue"]} for r in records if r["manual_queue"]]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("manifests", nargs="+", type=Path)
    args = parser.parse_args()
    report = batch(args.manifests, args.project_root)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    raise SystemExit(1 if report["counts"]["invalid"] else 0)


if __name__ == "__main__":
    main()
