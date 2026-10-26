#!/usr/bin/env python3
"""Local, read-only audio measurements. Technical pass is NEVER listening approval.

Requires Python 3 and ffmpeg/ffprobe, no Python packages, models, or network API.
Use --help and README.md for the report contract and heuristic limits.
"""
import argparse
import array
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

SCHEMA_VERSION = "audio-technical-report.v1"
TOOL_VERSION = "1.0.0"
# Project starting points, NOT industry standards or perceptual acceptance criteria.
DEFAULT_POLICY = {
    "max_sample_peak_dbfs": -1.0,
    "max_abs_dc_offset": 0.01,
    "near_full_scale_linear": 0.999969482421875,
    "silence_threshold_dbfs": -60.0,
    "silence_min_duration_s": 0.1,
    "max_leading_silence_s": 0.1,
    "max_trailing_silence_s": 0.25,
    "max_internal_silence_s": 0.25,
    "loop_boundary_jump_dbfs": -35.0,
    "loop_boundary_ratio": 8.0,
    "loop_context_s": 0.02,
    "max_decoded_bytes": 268435456,
    "timeout_s": 120,
}
LIMIT_CLAIMS = [
    "Measurements only; no human or AI listening was performed by this tool.",
    "Technical pass is not semantic, artistic, realism, licensing, or user acceptance.",
    "Near-full-scale samples indicate risk, not proof of audible clipping.",
    "Silence is a configured sample-amplitude test, not perceived silence.",
    "Loop risk is a heuristic at the declared whole-file boundary, not proof of a click or a seamless loop.",
    "No true-peak, LUFS, browser timing, runtime gain, bus effects, or mixed-scene measurements are claimed.",
]


def dbfs(value):
    """JSON null represents zero amplitude (-infinity dBFS)."""
    return round(20.0 * math.log10(value), 6) if value > 0 else None


def policy_with(overrides=None):
    result = dict(DEFAULT_POLICY)
    for key, value in (overrides or {}).items():
        if key not in result:
            raise ValueError("Unknown policy key: " + key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("Policy values must be finite numbers: " + key)
        result[key] = value
    for key, value in result.items():
        if key.startswith("max_") and key.endswith("silence_s"):
            if value < 0:
                raise ValueError("Silence allowance cannot be negative: " + key)
        elif key.endswith("_s") or key in ("max_decoded_bytes", "loop_boundary_ratio", "near_full_scale_linear"):
            if value <= 0:
                raise ValueError("Policy value must be positive: " + key)
    if not 0 < result["near_full_scale_linear"] <= 1:
        raise ValueError("near_full_scale_linear must be in (0, 1]")
    if result["max_abs_dc_offset"] < 0:
        raise ValueError("max_abs_dc_offset cannot be negative")
    if int(result["max_decoded_bytes"]) != result["max_decoded_bytes"]:
        raise ValueError("max_decoded_bytes must be an integer")
    # Finite dB input alone does not guarantee a representable linear threshold.
    for key in ("silence_threshold_dbfs", "loop_boundary_jump_dbfs"):
        try:
            linear = 10 ** (result[key] / 20)
        except OverflowError:
            raise ValueError("Policy dB threshold cannot be represented as linear amplitude: " + key) from None
        if not math.isfinite(linear) or linear <= 0:
            raise ValueError("Policy dB threshold cannot be represented as linear amplitude: " + key)
    if result["timeout_s"] > 86400:
        raise ValueError("timeout_s must not exceed the local subprocess resource limit of 86400 seconds")
    return result


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command, timeout):
    return subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, timeout=timeout, check=False)


def tool_version(binary):
    proc = run([binary, "-version"], 10)
    if proc.returncode:
        raise ValueError("Cannot run " + binary)
    return proc.stdout.splitlines()[0]


def add_finding(asset, severity, code, message):
    asset["findings"].append({"severity": severity, "code": code, "message": message})


def finish_asset(asset):
    severities = {item["severity"] for item in asset["findings"]}
    asset["technical_status"] = "fail" if "error" in severities else "warn" if "warning" in severities else "pass"
    return asset


def measure_samples(samples, channels, rate, policy, is_loop):
    """Measure decoded interleaved float32 samples without downmixing channels."""
    if not samples or len(samples) % channels:
        raise ValueError("Empty or incomplete decoded PCM frames")
    if any(not math.isfinite(value) for value in samples):
        raise ValueError("Decoded PCM contains NaN or infinity")
    frames = len(samples) // channels
    duration = frames / rate
    channel_metrics = []
    loop_channels = []
    # Clamp before multiplying; huge finite contexts cannot overflow round()
    # or inspect samples outside this file.
    window = max(2, min(frames, round(rate * min(policy["loop_context_s"], duration))))
    for channel in range(channels):
        values = samples[channel::channels]
        peak = max(abs(value) for value in values)
        rms = math.sqrt(math.fsum(value * value for value in values) / frames)
        dc = math.fsum(values) / frames
        channel_metrics.append({
            "channel": channel + 1,
            "sample_peak_linear": peak,
            "sample_peak_dbfs": dbfs(peak),
            "rms_linear": rms,
            "rms_dbfs": dbfs(rms),
            "dc_offset": dc,
            "near_full_scale_samples": sum(abs(v) >= policy["near_full_scale_linear"] for v in values),
            "over_full_scale_samples": sum(abs(v) > 1.0 for v in values),
        })
        if is_loop:
            jump = abs(values[0] - values[-1])
            context = [values[:window], values[-window:]]
            deltas = [part[i] - part[i - 1] for part in context for i in range(1, len(part))]
            local_rms = math.sqrt(math.fsum(v * v for v in deltas) / len(deltas)) if deltas else 0.0
            # null ratio + nonzero jump means flat context with a boundary step.
            ratio = jump / local_rms if local_rms > 0 else None
            risky = jump > 10 ** (policy["loop_boundary_jump_dbfs"] / 20) and (
                ratio is None or ratio > policy["loop_boundary_ratio"])
            loop_channels.append({
                "channel": channel + 1,
                "boundary_jump_linear": jump,
                "boundary_jump_dbfs": dbfs(jump),
                "local_delta_rms": local_rms,
                "ratio_to_local_delta_rms": ratio,
                "risk_flagged": risky,
            })
    # A frame is silent only if every channel is below the threshold. Never
    # downmix: phase-cancelled stereo would otherwise look like false silence.
    threshold = 10 ** (policy["silence_threshold_dbfs"] / 20)
    silence = []
    start = None
    for frame in range(frames + 1):
        quiet = frame < frames and all(abs(samples[frame * channels + c]) <= threshold for c in range(channels))
        if quiet and start is None:
            start = frame
        elif not quiet and start is not None:
            length = (frame - start) / rate
            if length >= policy["silence_min_duration_s"]:
                kind = "full_file" if start == 0 and frame == frames else "leading" if start == 0 else "trailing" if frame == frames else "internal"
                silence.append({"start_s": start / rate, "end_s": frame / rate,
                                "duration_s": length, "kind": kind})
            start = None
    peak = max(item["sample_peak_linear"] for item in channel_metrics)
    rms = math.sqrt(math.fsum(item["rms_linear"] ** 2 for item in channel_metrics) / channels)
    metrics = {
        "decoded_frames": frames,
        "decoded_duration_s": duration,
        "sample_peak_linear": peak,
        "sample_peak_dbfs": dbfs(peak),
        "rms_linear": rms,
        "rms_dbfs": dbfs(rms),
        "max_abs_dc_offset": max(abs(item["dc_offset"]) for item in channel_metrics),
        "near_full_scale_samples": sum(item["near_full_scale_samples"] for item in channel_metrics),
        "over_full_scale_samples": sum(item["over_full_scale_samples"] for item in channel_metrics),
        "channels": channel_metrics,
        "silence_intervals": silence,
        "true_peak_dbfs": None,
        "integrated_lufs": None,
        "loudness_status": "not_measured",
    }
    loop_risk = {
        "status": "risk_flagged" if any(c["risk_flagged"] for c in loop_channels) else "no_risk_flagged" if is_loop else "not_requested",
        "method": "whole-file boundary jump versus local first-difference RMS; amplitude AND ratio gates",
        "boundary": "whole_file" if is_loop else None,
        "channels": loop_channels,
        "perception_verified": False,
    }
    return metrics, loop_risk


def audit_asset(spec, base_dir, policy, ffmpeg="ffmpeg", ffprobe="ffprobe"):
    effective = policy_with({**policy, **spec.get("policy", {})})
    path = (base_dir / spec["path"]).resolve()
    asset = {
        "id": spec.get("id", spec["path"]), "path": spec["path"],
        "category": spec.get("category", "unspecified"), "loop": spec.get("loop", False),
        "source_sha256": None, "policy": effective,
        "decode": {"status": "not_run", "error": None}, "format": {}, "metrics": {},
        "loop_risk": {"status": "not_assessed", "perception_verified": False}, "findings": [],
        "evidence_kind": "local_decoded_pcm_measurement", "perception_verified": False,
        "listening_status": "not_assessed",
    }
    try:
        if not path.is_file():
            raise ValueError("Input is not a readable local file")
        asset["source_sha256"] = file_sha256(path)
        probe = run([ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe", "-show_streams",
                     "-show_format", "-of", "json", str(path)], effective["timeout_s"])
        if probe.returncode:
            raise ValueError("ffprobe failed: " + probe.stderr.strip()[-2000:])
        details = json.loads(probe.stdout)
        streams = [s for s in details.get("streams", []) if s.get("codec_type") == "audio"]
        if not streams:
            raise ValueError("No audio stream found")
        if len(streams) > 1:
            add_finding(asset, "warning", "multiple_audio_streams", "Only the first audio stream is measured.")
        stream = streams[0]
        channels, rate = int(stream["channels"]), int(stream["sample_rate"])
        if not 0 < channels <= 64 or not 0 < rate <= 768000:
            raise ValueError("Unsupported channel count or sample rate")
        raw_duration = stream.get("duration", details.get("format", {}).get("duration"))
        duration = float(raw_duration) if raw_duration not in (None, "N/A") else None
        if duration is not None and (not math.isfinite(duration) or duration < 0):
            raise ValueError("Invalid declared duration")
        asset["format"] = {"codec": stream.get("codec_name"), "container": details.get("format", {}).get("format_name"),
                           "sample_format": stream.get("sample_fmt"), "sample_rate_hz": rate,
                           "channels": channels, "duration_s": duration, "audio_streams": len(streams)}
        cap = int(effective["max_decoded_bytes"])
        if duration is not None and duration * channels * rate * 4 >= cap:
            raise ValueError("Declared decoded size exceeds configured local analysis limit")
        with tempfile.TemporaryDirectory(prefix="audio-audit-") as folder:
            pcm = Path(folder) / "decoded.f32le"
            decoded = run([ffmpeg, "-nostdin", "-v", "error", "-xerror", "-protocol_whitelist", "file,pipe",
                           "-i", str(path), "-map", "0:a:0", "-vn", "-sn", "-dn", "-f", "f32le",
                           "-c:a", "pcm_f32le", "-fs", str(cap), str(pcm)], effective["timeout_s"])
            if decoded.returncode:
                raise ValueError("ffmpeg decode failed: " + decoded.stderr.strip()[-2000:])
            if pcm.stat().st_size >= cap:
                raise ValueError("Decoded output reached configured local analysis limit; no partial pass")
            samples = array.array("f")
            with pcm.open("rb") as source:
                samples.fromfile(source, pcm.stat().st_size // 4)
            if sys.byteorder != "little":
                samples.byteswap()
            metrics, loop = measure_samples(samples, channels, rate, effective, asset["loop"])
        if file_sha256(path) != asset["source_sha256"]:
            raise ValueError("Input changed during measurement; discard this result and retry")
        asset.update(metrics=metrics, loop_risk=loop)
        asset["decode"] = {"status": "passed", "error": None}
        # Boundaries are measurements of decoded sample values, not judgements of taste.
        if metrics["over_full_scale_samples"]:
            add_finding(asset, "error", "over_full_scale", "Decoded float samples exceed digital full scale.")
        if metrics["sample_peak_dbfs"] is not None and metrics["sample_peak_dbfs"] > effective["max_sample_peak_dbfs"]:
            add_finding(asset, "warning", "peak_above_project_limit", "Sample peak exceeds the explicit project starting-point limit.")
        if metrics["near_full_scale_samples"]:
            add_finding(asset, "warning", "near_full_scale", "Near-full-scale samples found; this alone does not prove clipping.")
        if metrics["max_abs_dc_offset"] > effective["max_abs_dc_offset"]:
            add_finding(asset, "warning", "dc_offset", "A channel exceeds the configured absolute DC-offset limit.")
        for gap in metrics["silence_intervals"]:
            key = "max_" + gap["kind"] + "_silence_s"
            if gap["kind"] == "full_file" or gap["duration_s"] > effective[key]:
                add_finding(asset, "warning", "silence_" + gap["kind"],
                            "Configured low-amplitude interval %.6f–%.6f s; verify against intended silence." % (gap["start_s"], gap["end_s"]))
        if loop["status"] == "risk_flagged":
            add_finding(asset, "warning", "loop_boundary_risk", "Whole-file seam exceeds both heuristic gates; listening is required.")
    except (ValueError, OSError, KeyError, EOFError, subprocess.SubprocessError) as exc:
        asset["decode"] = {"status": "failed", "error": str(exc)}
        add_finding(asset, "error", "decode_or_measurement_failed", str(exc))
    return finish_asset(asset)


def validate_specs(specs):
    if not isinstance(specs, list) or not specs:
        raise ValueError("Provide at least one asset")
    ids = set()
    for spec in specs:
        if not isinstance(spec, dict) or not isinstance(spec.get("path"), str) or not spec["path"]:
            raise ValueError("Each asset needs a nonempty local path string")
        if "id" in spec and (not isinstance(spec["id"], str) or not spec["id"]):
            raise ValueError("Asset id must be a nonempty string")
        if "category" in spec and not isinstance(spec["category"], str):
            raise ValueError("Asset category must be a string")
        if not isinstance(spec.get("loop", False), bool):
            raise ValueError("loop must be a JSON boolean")
        if not isinstance(spec.get("policy", {}), dict):
            raise ValueError("Asset policy must be an object")
        policy_with(spec.get("policy"))
        identity = spec.get("id", spec["path"])
        if identity in ids:
            raise ValueError("Duplicate asset id: " + identity)
        ids.add(identity)


def build_report(specs, base_dir, overrides=None, ffmpeg="ffmpeg", ffprobe="ffprobe"):
    validate_specs(specs)
    policy = policy_with(overrides)
    versions = {"audio_audit": TOOL_VERSION, "python": sys.version.split()[0],
                "ffmpeg": tool_version(ffmpeg), "ffprobe": tool_version(ffprobe)}
    assets = [audit_asset(s, base_dir, policy, ffmpeg, ffprobe) for s in specs]
    return {"schema_version": SCHEMA_VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
            "tool_versions": versions, "policy": policy,
            "policy_basis": "Explicit configurable project starting points; not a universal audio standard.",
            "evidence_kind": "local_decoded_pcm_measurement", "perception_verified": False,
            "listening_status": "not_assessed", "limit_claims": LIMIT_CLAIMS,
            "assets": assets,
            "summary": {"assets": len(assets), **{status: sum(a["technical_status"] == status for a in assets)
                                                   for status in ("pass", "warn", "fail")}}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="Local files; do not combine with --manifest")
    parser.add_argument("--manifest", type=Path, help="JSON object with assets[] and optional policy{}")
    parser.add_argument("--policy", type=Path, help="JSON policy overrides, applied after manifest policy")
    parser.add_argument("--base-dir", type=Path, default=Path.cwd(), help="Resolve asset paths here; default is current directory")
    parser.add_argument("--loop", action="store_true", help="For positional files, inspect the whole-file loop seam")
    parser.add_argument("--output", type=Path, help="Write JSON here instead of stdout; never overwrites an input")
    parser.add_argument("--fail-on-warning", action="store_true", help="Exit 1 on warning as well as failure")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args(argv)
    try:
        if args.manifest and (args.files or args.loop):
            raise ValueError("--manifest cannot be combined with positional files or --loop")
        manifest = json.loads(args.manifest.read_text()) if args.manifest else {}
        if not isinstance(manifest, dict):
            raise ValueError("Manifest must be an object")
        specs = manifest.get("assets", []) if args.manifest else [{"path": f, "loop": args.loop} for f in args.files]
        overrides = manifest.get("policy", {})
        if not isinstance(overrides, dict):
            raise ValueError("Manifest policy must be an object")
        if args.policy:
            overrides = {**overrides, **json.loads(args.policy.read_text())}
        validate_specs(specs)
        inputs = {(args.base_dir / s["path"]).resolve() for s in specs}
        inputs.update(p.resolve() for p in (args.manifest, args.policy) if p)
        aliases_input = args.output and (args.output.resolve() in inputs or (
            args.output.exists() and any(p.exists() and args.output.samefile(p) for p in inputs)))
        if aliases_input:
            raise ValueError("Report output must not overwrite an input")
        report = build_report(specs, args.base_dir.resolve(), overrides, args.ffmpeg, args.ffprobe)
        content = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content)
        else:
            print(content, end="")
        return 1 if report["summary"]["fail"] or (args.fail_on_warning and report["summary"]["warn"]) else 0
    except (ValueError, TypeError, OverflowError, OSError, subprocess.SubprocessError) as exc:
        print("audio_audit: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
