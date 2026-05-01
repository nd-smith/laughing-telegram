# 0002 — Envelope construction

## Goal

Pure module that wraps a raw event in the standard envelope per PRD §Envelope Schema.

## Scope

- `pipeline/envelope.py` exposing a function `build_envelope(...)` that returns a dict matching the schema in PRD §Envelope Schema exactly.
- Module-level constant `SCHEMA_VERSION = "1.0"`.
- `envelope_id` generated as UUID v4.
- `processed_at` set inside the function; `processing_ms` calculated from received-at to processed-at.
- `tests/test_envelope.py` covering:
  - All required envelope fields populated.
  - `envelope_id` is a valid UUID v4.
  - `correlation_id` set when extracted, `null` otherwise.
  - `received_at` ≤ `processed_at`; `processing_ms` ≥ 0.
  - `payload` preserved byte-equivalent to input.
  - `schema_version` matches the constant.

## Out of scope

- Validation logic (issue 0003).
- Per-source extractor logic (issue 0004 / future per-source issues).
- Any I/O — pure functions only, no global state.

## Acceptance criteria

- `tests/test_envelope.py` passes.
- `build_envelope(...)` accepts the inputs needed to populate every envelope field that does *not* originate inside the function itself (raw event / metadata / event type / correlation_id / source.system / source.event_hub / source.original_timestamp / pipeline_id / retry_count / received_at).

## Notes

- **Ask before deciding** the function signature shape (positional, keyword-only, or a small dataclass for inputs). Lean simplest.
- Do not import any pipeline I/O modules here — keep the module dependency-free aside from stdlib.
