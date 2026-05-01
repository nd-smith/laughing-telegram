# 0006 — `build_envelope` uses keyword-only arguments

**Status:** Accepted
**Date:** 2026-05-01

## Context

Issue [0002](../issues/complete/0002_envelope_construction.md) creates `pipeline/envelope.py` with a single `build_envelope(...)` function. The function needs ~9 caller-supplied inputs (raw event, metadata, event type, correlation_id, source system / event hub / original_timestamp, pipeline_id, retry_count, received_at). The issue's Notes flagged the signature shape as an "ask before deciding" item. Three options were on the table:

- **Positional arguments.** With nine inputs, call sites become a long unlabelled list — error-prone and unreadable. Several inputs are strings of similar shape (source_system, source_event_hub, pipeline_id, event_type), so swapped arguments would type-check and silently corrupt envelopes.
- **Keyword-only arguments** (`def build_envelope(*, raw_event, metadata, ...)`). Call sites are self-documenting; argument order doesn't matter; misnamed args fail loudly at the call boundary. Stdlib only, no extra type to maintain.
- **Small dataclass for inputs** (e.g., `EnvelopeInputs`). Groups the inputs into a named container, but introduces a second concept callers must import and construct just to call one function. With a single call site per worker (the processing loop), the grouping pays for itself rarely.

The repo's guiding principle is simplicity-first for non-expert maintainers and AI-assisted troubleshooting. The dataclass adds an indirection that buys little here; positional args are unsafe at this arity.

## Decision

`build_envelope` takes all nine caller-supplied inputs as **keyword-only arguments**. The function generates `envelope_id`, `processed_at`, and `processing_ms` internally and returns the assembled envelope dict.

## Consequences

- Call sites are explicit: every value is named at the point of call, which makes the processing-loop wiring readable without jumping back to the function definition.
- Argument-order mistakes are impossible; misnamed kwargs raise `TypeError` immediately.
- No extra type to import alongside the function; the module stays stdlib-only.
- If the input set grows substantially in the future (say, beyond ~12 fields) and call sites become unwieldy, revisiting with a dataclass remains a low-cost refactor — all current call sites are inside this repo.
