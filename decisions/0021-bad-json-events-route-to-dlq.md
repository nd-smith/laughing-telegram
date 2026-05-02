# 0021 — Bad-JSON events route to DLQ via validator rejection

**Status:** Accepted
**Date:** 2026-05-02

## Context

Issue [0011](../issues/complete/0011_worker_entry_point_and_main_loop.md) wires the worker's per-event callback. The callback gets an `azure.eventhub.EventData` instance from `EventHubConsumer` and must hand a parsed dict + `received_at` timestamp to `Processor.process(...)`. `EventData.body_as_json()` raises on malformed JSON, and the callback has to decide what happens then.

Two options:

- **(a) Let the exception escape the callback.** `EventHubConsumer` (ADR 0011) catches callback exceptions, logs `"callback raised; skipping checkpoint"`, and continues. The bad event is never checkpointed and will be re-delivered indefinitely on the next session.
- **(b) Catch in the callback and substitute a non-dict value.** Fall back to `event.body_as_str()` (or `repr(event.body)` when even that fails) and pass the result into `processor.process(...)`. The processor's `validate(...)` rejects non-dict input on the first attempt; the retry loop runs to exhaustion; the event lands in `propgateway.{source}.dlq` with the parse error captured in the DLQ payload's `error` and `stack_trace` fields.

PRD §3 lists "Is valid JSON" as a validation concern, and §Error Handling routes validation failures into the DLQ. Option (a) does not satisfy that — a single malformed event would silently block forward progress on its partition. Option (b) routes malformed events through the same path as every other validation failure, making bad JSON observable via `events_dlq_total` and the DLQ topic.

The cost of (b) is a few seconds of doomed retries per malformed event (1s + 2s + 4s with the default backoff per ADR 0019) and a slightly weaker DLQ payload — `raw_event` is a string, not a dict. Both are acceptable: malformed JSON is expected to be rare, and the DLQ consumer already has to be tolerant of variable `raw_event` shapes since validation also fires on dicts that pass JSON parsing but lack required fields.

## Decision

The entry-point callback wraps `event.body_as_json()` in a `try/except`. On failure it logs a warning with `exc_info=True`, then attempts `event.body_as_str()`; if that also raises, it uses `repr(getattr(event, "body", event))` as a last-resort string. The resulting non-dict value is passed verbatim into `processor.process(raw_event, received_at)`, where the standard validate → retry → DLQ flow takes over.

## Consequences

- Malformed-JSON events end up in the source's DLQ topic on the same path as every other validation failure. Operators see them via `events_dlq_total` and the DLQ topic; no new code path to monitor.
- The worker keeps making progress on its Event Hub partition — no livelock from a single bad message.
- Each malformed event spends ~7 seconds (1 + 2 + 4 with default backoff) failing retries before reaching the DLQ. For the expected volume of bad JSON this is fine; if real-world rates make it a problem, `Processor`'s `max_retries` and `backoff_base_s` are already configurable per ADR 0019.
- The DLQ payload's `raw_event` field will be a string for parse failures and a dict for everything else. Out-of-scope DLQ consumers must handle both shapes. This was already implicit since `validate(...)` accepts `Any`.
- The fallback `body_as_str` / `repr` chain is deliberately narrow: it produces a string rather than re-raising, so the DLQ publish itself can't fail on a non-JSON-serializable input (the strict-JSON serialisation policy of ADR 0016 still holds for the DLQ topic).
