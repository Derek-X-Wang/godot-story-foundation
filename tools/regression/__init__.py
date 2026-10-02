"""Optional, standard-library-only regression execution and coverage contracts."""

from .runner import (
    ContractError,
    begin_report,
    inspect_log,
    load_manifest,
    run_command,
    run_manifest,
    run_suite,
    validate_manifest,
    validate_result,
)

__all__ = [
    "ContractError", "begin_report", "inspect_log", "load_manifest", "run_command", "run_manifest", "run_suite",
    "validate_manifest", "validate_result",
]
__version__ = "0.1.0"
