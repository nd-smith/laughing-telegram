# 0011 — Event Hub consumer callback shape: single-event

**Status:** Accepted
**Date:** 2026-05-02

## Context

Issue [0007](../issues/complete/0007_event_hub_consumer.md) adds `pipeline/consumer.py`. The consumer wraps the sync `azure-eventhub` SDK and hands events off to the rest of the pipeline (validation, envelope, write, publish). The PRD §Pipeline Components §2 describes the consumer as: "Reads events in batches. Passes each event to the processing pipeline." The issue's Notes flagged the precise callback API as an "ask before deciding" item. Three options were considered:

- **Single-event callback `callback(event)`.** The consumer invokes the callback once per event, in receive order. Matches the PRD wording most directly. Pairs cleanly with the per-event retry/DLQ flow in issue 0010 (each event has its own success/failure outcome), and with after-success checkpointing (the consumer can update the checkpoint immediately after one event is processed, not after a whole batch). Simplest mental model for non-expert maintainers — one event in, one decision out.
- **Batch callback `callback(events)`.** Hands the SDK's batch through unchanged. Gives downstream control over batching, but the writer (issue 0008) already does its own time/size-based batching for the OneLake flush, and the publisher (issue 0009) is per-event anyway. So this option just adds a layer that re-fans-out to per-event work in 0010, while complicating retry semantics (what if event 4 of 10 fails — partial success? whole-batch retry?).
- **Generator yielding events.** Inverts control: the caller drives the loop. Doesn't compose with the SDK's `on_event=` callback model — would require an internal queue and a worker thread translating callback-push into generator-pull. Real complexity for no gain over option 1.

The repo's guiding principle is simplicity-first; the project's hard constraint is sync + threading. The single-event callback is the simplest option that also honours those constraints, and it fits the PRD wording verbatim.

## Decision

`EventHubConsumer.run(callback, shutdown)` invokes `callback(event)` exactly once per non-`None` event delivered by the SDK, in the order the SDK delivers them. The callback receives the SDK's `EventData` object directly — body parsing is the callback's responsibility (the validator and per-source extractor in later issues already need that flexibility). If the callback returns normally, the consumer calls `partition_context.update_checkpoint(event)` for that event. If the callback raises, the consumer logs the exception, leaves the checkpoint unchanged, and continues consuming subsequent events; retry / DLQ semantics are owned by issue 0010's wrapper callback, not by this module.

## Consequences

- One event in, one checkpoint decision out — the unit-test surface stays small and the production failure mode (callback raises) is unambiguous.
- The consumer never has to reason about partial-batch outcomes; that complexity is pushed to where it belongs (the per-event retry wrapper in 0010).
- The callback receives the raw `EventData`, so callers can choose `body_as_json()`, `body_as_str()`, or raw bytes per source needs — the consumer does not pre-decide the body shape.
- If a future source genuinely needs batch-level decisions (e.g. transactional writes spanning multiple events), this contract is too narrow and the consumer would need a second method. Acceptable: that case isn't on the roadmap and adding a method later is a low-cost refactor.
