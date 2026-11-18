"""Render provider-neutral review-only regions against exact PNG source bytes.

Standard library only. Never runs a model, changes sources, approves art, or
participates in a game build. Private inputs/output belong outside export roots.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import html
import json
import math
from pathlib import Path
import re
import shutil
import struct
from ..png import decode, MAX_PIXELS

MAX_IMAGE = 20 * 1024 * 1024
MAX_PACKET = 4 * 1024 * 1024
MAX_TOTAL_PIXELS = 16_777_216
NAME = re.compile(r"[A-Za-z0-9_-]{1,80}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def prepare(packet_path: Path, sources_root: Path):
    require(packet_path.stat().st_size <= MAX_PACKET, "packet exceeds size limit")
    raw = packet_path.read_bytes()
    packet = json.loads(raw)
    require(isinstance(packet, dict), "packet must be an object")
    require(packet.get("schema") == "portrait-local-review-v1", "unsupported schema")
    require(packet.get("mode") == "review_only" and packet.get("automatic_approval") is False,
            "only non-approving review packets are supported")
    records = packet.get("records")
    require(isinstance(records, list) and 1 <= len(records) <= 100, "expected 1..100 records")
    root = sources_root.resolve(strict=True)
    prepared = []
    seen = set()
    total = 0
    total_pixels = 0
    for record in records:
        require(isinstance(record, dict), "record must be an object")
        name = record.get("name")
        require(isinstance(name, str) and NAME.fullmatch(name), "invalid record name")
        require(name not in seen, "duplicate record name")
        seen.add(name)
        require("automatic_anatomy_verdict" in record and record["automatic_anatomy_verdict"] is None,
                "anatomy verdicts are not supported")
        require(record.get("projection_depth") == "unobservable", "depth cannot be inferred by this adapter")
        digest = record.get("source_sha256")
        require(isinstance(digest, str) and SHA.fullmatch(digest), "invalid source hash")
        source = (root / (name + ".png")).resolve(strict=True)
        require(source.is_relative_to(root), "source escapes sources root")
        require(source.is_file() and source.stat().st_size <= MAX_IMAGE, "invalid source size/type")
        data = source.read_bytes()
        total += len(data)
        require(total <= 100 * 1024 * 1024, "batch exceeds source byte budget")
        require(hashlib.sha256(data).hexdigest() == digest, "source hash mismatch: " + name)
        require(len(data) >= 33 and data[:8] == b"\x89PNG\r\n\x1a\n" and
                data[8:12] == b"\x00\x00\x00\r" and data[12:16] == b"IHDR", "expected PNG IHDR")
        width, height = struct.unpack(">II", data[16:24])
        require(0 < width <= 16384 and 0 < height <= 16384 and width * height <= MAX_PIXELS,
                "PNG dimensions exceed budget")
        total_pixels += width * height
        require(total_pixels <= MAX_TOTAL_PIXELS, "batch exceeds decoded pixel budget")
        require(record.get("source_size") == [width, height], "source dimension mismatch")
        decode(data)  # shared bounded codec checks CRC, chunks, zlib, filters and pixels

        regions = record.get("regions")
        require(isinstance(regions, list) and len(regions) <= 100, "invalid region list")
        for region in regions:
            require(isinstance(region, dict), "region must be an object")
            box = region.get("bbox_normalized_xyxy")
            require(isinstance(box, list) and len(box) == 4 and
                    all(type(v) in (int, float) and math.isfinite(v) and 0 <= v <= 1 for v in box),
                    "invalid normalized box")
            require(box[0] < box[2] and box[1] < box[3], "empty/inverted box")
            for field in ("kind", "reason", "action"):
                require(isinstance(region.get(field), str) and len(region[field]) <= 1000,
                        "invalid region text")
        for field in ("status", "pose_gate", "semantic_gate"):
            require(isinstance(record.get(field), str) and len(record[field]) <= 1000,
                    "invalid status text")
        prepared.append((record, data))
    return hashlib.sha256(raw).hexdigest(), prepared


def render(prepared):
    cards = []
    esc = html.escape
    for record, data in prepared:
        boxes, reasons = [], []
        for index, region in enumerate(record["regions"], 1):
            x0, y0, x1, y1 = region["bbox_normalized_xyxy"]
            boxes.append(f'<span class="box" style="left:{x0*100:.6f}%;top:{y0*100:.6f}%;'
                         f'width:{(x1-x0)*100:.6f}%;height:{(y1-y0)*100:.6f}%">{index}</span>')
            reasons.append(f'<li>{esc(region["kind"])}: {esc(region["reason"])}. '
                           f'{esc(region["action"])}</li>')
        image = base64.b64encode(data).decode("ascii")
        cards.append(f'<article><h2>{esc(record["name"])}</h2><p>{esc(record["status"])}</p>'
                     f'<div class="portrait"><img loading="lazy" alt="{esc(record["name"], quote=True)}" '
                     f'src="data:image/png;base64,{image}">{"".join(boxes)}</div>'
                     f'<p>Pose: {esc(record["pose_gate"])}<br>Semantic: '
                     f'{esc(record["semantic_gate"])}</p><ol>{"".join(reasons)}</ol>'
                     f'<small>SHA256 {record["source_sha256"]}</small></article>')
    return ('<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            'img-src data:; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>Portrait local review</title><style>'
            'body{font:16px sans-serif;background:#eee;color:#17202a;margin:24px}'
            'main{display:flex;flex-wrap:wrap;gap:24px}article{background:white;padding:16px;width:420px;max-width:100%;overflow-wrap:anywhere}'
            '.portrait{position:relative;width:100%;background:#ddd}.portrait img{display:block;width:100%;height:auto}'
            '.box{position:absolute;border:2px solid #a00088;box-sizing:border-box;color:#800070;font-weight:bold;pointer-events:none}'
            'small{font-size:11px}</style><h1>Review only. Not an anatomy verdict.</h1>'
            '<p>Depth is unobservable. Regions are supplied review candidates, not detected defects. '
            'No approval, repair, model execution or game-build gate is performed.</p><main>'
            + ''.join(cards) + '</main></html>')


def build(packet_path: Path, sources_root: Path, output: Path):
    packet_hash, prepared = prepare(packet_path, sources_root)
    document = render(prepared)
    summary = {"schema": "portrait-review-build-v1", "packet_sha256": packet_hash,
               "mode": "review_only", "automatic_approval": False,
               "records": [{"name": r["name"], "source_sha256": r["source_sha256"],
                            "status": r["status"], "region_count": len(r["regions"])} for r, _ in prepared]}
    # Exclusive directory creation: never replace an existing review or source.
    output.mkdir(parents=False, exist_ok=False)
    try:
        (output / "report.html").write_text(document, encoding="utf-8")
        (output / "review-build.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    except BaseException:
        shutil.rmtree(output)
        raise
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--sources-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary = build(args.packet, args.sources_root, args.output)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f"review input/build error: {error}\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
