---
name: 0018 — DLQ payload is a flat dict, not an envelope
description: Dead-letter messages are the literal four PRD §Dead Letter Queue fields (raw_event, error, stack_trace, retry_count, failed_at) in a flat dict; rejected wrapping in the standard envelope
type: project
---

# 0018 — DLQ payload is a flat dict, not an envelope

**Status:** Accepted
**Date:** 2026-05-02

## Context

Issue [0010](../issues/complete/0010_processing_pipeline_and_retry_dlq.md) introduces the dead-letter publish path: after retry exhaustion, the processor publishes a payload describing the failure to `propgateway.{source-name}.dlq`. The issue's Notes flagged the payload shape as an "ask before deciding" item with two candidates:

- **Wrap the failure in the standard envelope.** Symmetrical with the success path (every Kafka message published by the pipeline is enveloped). Costs: the envelope build itself can be the failing step, in which case the DLQ would call back into the same `build_envelope` that just raised. Even when envelope build succeeded and the failure is downstream, the envelope's `metadata` is per-source-extracted and may be partial or absent on retry. Forcing the DLQ payload to fit the envelope schema means inventing values for fields the failure has no answer to (`event.processed_at` of a thing that did not process; `pipeline.processing_ms` of a thing that was retried with sleeps; `metadata` of an event whose extractor never ran).
- **Flat dict matching PRD §Dead Letter Queue verbatim.** PRD lists four bullets: original raw event, error message and stack trace, retry count, timestamp of final failure. A flat dict with `raw_event`, `error`, `stack_trace`, `retry_count`, `failed_at` is what those bullets describe. The DLQ path depends on no other module's code path having succeeded.

CLAUDE.md's project instructions say: "Read the PRD literally" — and the issue's own note repeats this. The literal reading is the four-field flat dict.

## Decision

The DLQ payload is a flat dict with these keys, published to `propgateway.{source-name}.dlq`:

```
{
  "raw_event":   <the original raw event dict the consumer handed in>,
  "error":       <str(exception) of the last failing attempt>,
  "stack_trace": <traceback.format_exception(...) of that exception>,
  "retry_count": <int — the number of retries attempted, equal to max_retries on exhaustion>,
  "failed_at":   <ISO8601 UTC string — datetime.now(timezone.utc).isoformat()>
}
```

It is not wrapped in the standard envelope. DLQ consumers (out of scope per PRD §Out of Scope) read this shape directly.

## Consequences

- The DLQ path runs whether the failing step was validate, extract, envelope-build, write, or publish. None of those need to have succeeded for the DLQ payload to be constructable.
- DLQ consumers can be written against a stable, small schema documented in the PRD itself, rather than against the envelope schema (which has fields that make no sense for a never-processed event).
- The Kafka publisher serialises with `json.dumps(...)` strictly (ADR 0016), so all DLQ-payload values must be JSON-native at construction time. `raw_event` is already a parsed dict; everything else is a primitive built locally.
- If a future DLQ-consumer needs envelope-compatible context (e.g., to share downstream tooling with the success-path consumers), this can be added as additional fields without breaking the four-field contract — the PRD bullets are a floor, not a ceiling.
