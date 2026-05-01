# 0005 — Structured JSON logging

## Goal

Centralised JSON logger setup that all pipeline modules use, with `source` / `correlation_id` / `envelope_id` propagated as contextual fields. Per PRD §Observability §Structured Logging.

## Scope

- `shared/logging.py` (cross-cutting — also usable by future `apps/`).
- A `setup_logging(source: str, level: str = "INFO")` function that configures stdlib `logging` to emit one JSON object per line to stdout.
- A mechanism for downstream code to attach `correlation_id` and `envelope_id` to log records for the duration of processing one event.
- Every emitted log line includes: `timestamp` (ISO8601 UTC), `level`, `source`, `correlation_id` (null if unset), `envelope_id` (null if unset), `message`, plus any structured extras.
- `tests/test_logging.py` covering:
  - Emitted line is valid JSON with all required keys.
  - `correlation_id` / `envelope_id` propagate when set; default to null otherwise.
  - Extra structured fields pass through.

## Out of scope

- File handlers, log shippers, log rotation. Stdout only — K8s collects.
- Log sampling, redaction, PII filters.

## Acceptance criteria

- Capturing stdout from a logger call yields valid JSON with the schema above.
- Context propagation works when set inside one logical event-processing scope and clears between scopes.
- `tests/test_logging.py` passes.

## Notes

- **Ask before deciding** the context-propagation mechanism: `contextvars` (cleanest for thread + future async) vs `LoggerAdapter` (simpler, per-call) vs explicit `extra=` dicts at every call site. This is a design decision worth an ADR.
- **Ask before adding a dep** like `python-json-logger`. A small custom `Formatter` subclass is usually enough; only add the dep if it materially simplifies the code.
