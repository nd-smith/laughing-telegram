# 0010 — Processing pipeline & retry/DLQ orchestration

## Goal

Glue the pure components (validation, source extractor, envelope builder) and the I/O components (writer, publisher) into a single per-event processing flow with the retry-3x-then-DLQ policy from PRD §Error Handling.

## Scope

- New module `pipeline/process.py` (name TBD — **ask** if a different name reads better) exposing a function or class that processes one raw event end-to-end:
  1. Validate the raw event (issue 0003).
  2. Run the source's `extract` (issue 0004) to get metadata + event type.
  3. Build the envelope (issue 0002).
  4. Add to the writer's buffer (issue 0008).
  5. Publish via the Kafka publisher (issue 0009) to the source's output topic.
- On any step's failure: retry up to **3 times** with exponential backoff (default base **1s**, doubling — i.e. 1s, 2s, 4s; configurable). Increment `pipeline.retry_count` in the envelope between attempts.
- After retry exhaustion: build a DLQ payload containing the original raw event, error message, stack trace, retry count, and final-failure timestamp; publish to `propgateway.{source-name}.dlq`. Increment `events_dlq_total`.
- On success: increment `events_processed_total{status="success"}`. On final failure: increment `events_processed_total{status="failure"}`.
- Records `processing_duration_seconds` per event.
- Logs each attempt and final outcome with `correlation_id` / `envelope_id` context.
- `tests/test_process.py` covering:
  - Happy path — all components called once, success metric incremented.
  - Validation failure — goes to DLQ after retries.
  - Extract / envelope / write / publish failure — each goes to DLQ after retries.
  - One transient failure then success — succeeds without DLQ.
  - Backoff timing — use a small/configurable backoff so tests stay fast.
  - DLQ payload structure matches PRD §Dead Letter Queue.
  - DLQ topic name matches `propgateway.{source-name}.dlq` exactly.

## Out of scope

- Consumer wiring — issue 0011.
- Threading / concurrency at this layer — single event at a time.
- Persistent state across worker restarts (Event Hub checkpointing handles that, owned by issue 0007).

## Acceptance criteria

- Function/class processes events end-to-end through real (mocked at SDK boundary) versions of the other components.
- All test cases above pass.
- Backoff base and max retries are configurable so tests don't need real sleeps and ops can tune later.

## Notes

- **Ask before deciding** the function vs. class shape. A class makes injecting writer/publisher cleaner; a function with explicit args is simpler. Lean simplest.
- **Ask** if DLQ payload should itself be wrapped in an envelope, or be a flat dict per PRD §Dead Letter Queue. Read the PRD literally.
- Confirm exponential-backoff defaults (1s/2s/4s) with the user before coding — PRD says "exponential backoff" but doesn't specify base.
