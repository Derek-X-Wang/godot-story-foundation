"""Offline regression CLI. Incomplete runs are never labeled passing."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .runner import ContractError, begin_report, load_manifest, run_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run trusted commands and write logs/report.json")
    run.add_argument("--manifest", required=True)
    run.add_argument("--output", required=True)
    policy = run.add_mutually_exclusive_group()
    policy.add_argument("--require-all", action="store_true",
                        help="explicit strict mode (the default): exit 3 for incomplete scope or coverage")
    policy.add_argument("--allow-incomplete", action="store_true",
                        help="report-only opt-in: exit 0 for incomplete runs; passed remains false")
    validate = commands.add_parser("validate", help="validate a manifest without running commands")
    validate.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            begin_report(args.output)
        path = Path(args.manifest).resolve()
        manifest = load_manifest(path)
        if args.command == "validate":
            print(json.dumps({"valid": True, "suites": len(manifest["suites"])}))
            return 0
        report = run_manifest(manifest, base_dir=path.parent, output_dir=args.output)
        print(json.dumps({"status": report["status"], "passed": report["passed"],
                          "complete": report["complete"], "execution_state": report["execution_state"],
                          "report": str((Path(args.output) / "report.json").resolve())}, sort_keys=True))
        if report["status"] == "failed":
            return 1
        if report["status"] == "incomplete" and not args.allow_incomplete:
            return 3
        return 0
    except (ContractError, OSError) as error:
        print("regression: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
