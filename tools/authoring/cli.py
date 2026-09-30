"""Command line interface; all operations are offline and fail closed."""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .validation import ValidationError
from . import workflow


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Offline Story Foundation authoring: export, import, validate, review, approve, build")
    p.add_argument("--version", action="version", version=__version__)
    commands = p.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export-request", help="export a provider-neutral JSON request; never calls a model")
    export.add_argument("--packet", required=True)
    export.add_argument("--output", required=True)
    imp = commands.add_parser("import-response", help="import raw response JSON into an unapproved candidate")
    imp.add_argument("--packet", required=True)
    imp.add_argument("--response", required=True)
    imp.add_argument("--model-declared", required=True, help="caller-declared provenance, or offline-fixture; not authenticated")
    imp.add_argument("--output", required=True)
    for name in ("validate", "simulate", "review", "approve", "build"):
        cmd = commands.add_parser(name)
        cmd.add_argument("--packet", required=True)
        cmd.add_argument("--candidate", required=True)
        if name in ("approve", "build"):
            cmd.add_argument("--review", required=True)
        if name in ("review", "approve", "build"):
            cmd.add_argument("--output", required=True)
        if name == "review":
            cmd.add_argument("--baseline", help="optional previous raw compiled content.json for a textual diff")
        elif name == "approve":
            cmd.add_argument("--reviewer", required=True)
            cmd.add_argument("--yes-i-reviewed", action="store_true", help="affirm that you personally reviewed this exact packet and candidate")
        elif name == "build":
            cmd.add_argument("--approval", required=True)
            cmd.add_argument("--allow-test-fixture", action="store_true", help="allow conspicuously labeled synthetic approval for public demo/tests only")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "export-request":
            workflow.export_request(args.packet, args.output)
            result = {"exported":True,"model_called":False}
        elif args.command == "import-response":
            workflow.import_response(args.packet, args.response, args.model_declared, args.output)
            result = {"imported":True,"review_status":"unapproved"}
        elif args.command in ("validate", "simulate"):
            result = workflow.validate_candidate(args.packet, args.candidate)
            if args.command == "simulate":
                result = result["simulation"]
        elif args.command == "review":
            result = workflow.create_review(args.packet, args.candidate, args.output, args.baseline)
            result = {"review_created":True,"review_status":"unapproved","coverage":result["simulation"]["coverage"]}
        elif args.command == "approve":
            workflow.approve(args.packet, args.candidate, args.review, args.reviewer, args.yes_i_reviewed, args.output)
            result = {"review_status":"approved","reviewer":args.reviewer}
        else:
            result = workflow.build(args.packet, args.candidate, args.review, args.approval, args.output, args.allow_test_fixture)
        print(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2))
        return 0
    except (ValidationError, OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        print("authoring: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
