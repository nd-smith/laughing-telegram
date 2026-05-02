# 0007 — Event Hub consumer

## Goal

Sync Event Hub consumer that delivers events from a source's hub to the pipeline with checkpointing. Per PRD §Pipeline Components §2.

## Scope

- `pipeline/consumer.py` exposing a class (e.g., `EventHubConsumer`) wrapping the **sync** `azure-eventhub` API.
- Authentication via `DefaultAzureCredential` from `azure-identity`. **No connection strings.**
- Construction: `(eventhub_namespace, eventhub_name, consumer_group, checkpoint_store_url)` plus any other args needed by the SDK; read from environment in the entry point (issue 0011), not here.
- Public surface: a method that runs a per-event processing callback supplied by the caller, checkpoints after the callback succeeds.
- Logs lifecycle events (connect, batch received, checkpoint, disconnect) using the shared logger from issue 0005.
- Increments `events_received_total` (from issue 0006) on each event read.
- `tests/test_consumer.py` mocking the SDK boundary — verify checkpointing happens after callback success and not on callback failure; verify metric increment.

## Out of scope

- Validation, envelope creation, write, publish — consumer just delivers raw events to a callback.
- Retry/DLQ — issue 0010.
- Provisioning the Blob Storage checkpoint store — assumed pre-existing.
- Tests against a real Event Hub.

## Acceptance criteria

- Consumer constructible from the inputs above.
- Run-loop method drives the SDK and invokes the callback per event with checkpointing.
- `tests/test_consumer.py` passes with the SDK mocked.

## Notes

- **Ask before deciding** the callback API shape (single-event callback, batch callback, or generator yielding events). PRD says "Reads events in batches. Passes each event to the processing pipeline" — single-event callback matches that most closely.
- **Ask** where graceful shutdown lives — inside the consumer's run loop or driven by a shutdown flag from the entry point (issue 0011). Surface the trade-off; don't pick silently.
- Sync SDK only — do not use `azure.eventhub.aio`.
