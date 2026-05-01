"""Minimal event validation per PRD §Pipeline Components §3.

Pure module: no I/O, no logging, no metrics, stdlib only. Required fields
are passed in by the caller — this module does not import source modules.
"""

from typing import Any, Iterable, NamedTuple


class ValidationResult(NamedTuple):
    ok: bool
    reason: str | None


def validate(raw_event: Any, required_fields: Iterable[str]) -> ValidationResult:
    """Check that `raw_event` is a dict containing every name in `required_fields`.

    Returns a `ValidationResult`. On failure, `reason` is a human-readable
    string suitable for log lines and DLQ payloads (it names the offending
    field when one is missing).
    """
    if not isinstance(raw_event, dict):
        return ValidationResult(False, f"raw_event must be a dict, got {type(raw_event).__name__}")

    for field in required_fields:
        if field not in raw_event:
            return ValidationResult(False, f"missing required field: {field!r}")

    return ValidationResult(True, None)
