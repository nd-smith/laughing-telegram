# 0003 — Event validation

## Goal

Minimal validation function that checks a raw event is a parsed JSON object containing the top-level fields a source extractor needs. Per PRD §Pipeline Components §3.

## Scope

- `pipeline/validation.py` exposing a function (e.g., `validate(raw_event, required_fields)`) returning a structured pass/fail result with a human-readable reason on failure.
- `tests/test_validation.py` covering:
  - Pass when raw_event is a dict containing all required fields.
  - Fail when raw_event is not a dict.
  - Fail when raw_event is `None`.
  - Fail when a required top-level field is missing — reason names the field.
  - Pass when `required_fields` is empty.

## Out of scope

- Schema validation libraries (`jsonschema`, `pydantic`). Keep it plain.
- Coupling to specific source modules — `validate` takes the required-fields list as an argument, it does not import sources.
- Retry/DLQ routing of failures (issue 0010).

## Acceptance criteria

- `tests/test_validation.py` passes.
- Failure result includes a `reason` field suitable for logging and DLQ payloads.

## Notes

- **Ask before deciding** result shape: tuple `(ok: bool, reason: str | None)` vs `NamedTuple` vs `dataclass`. Lean simplest that still reads clearly at call sites.
- Keep the function pure — no logging, no metrics, no I/O.
