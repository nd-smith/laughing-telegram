# 0009 — Kafka publisher

## Goal

Per-source Kafka producer that publishes envelopes (and DLQ messages) reliably. Per PRD §Pipeline Components §6.

## Scope

- `pipeline/publisher.py` exposing a class (e.g., `KafkaPublisher`) wrapping `confluent-kafka` `Producer`.
- Construction takes broker config + any auth details from the caller (entry point reads env vars in issue 0011).
- Public surface: `publish(topic: str, envelope: dict)` — JSON-serialises the envelope and publishes. Blocks until delivery is confirmed (or fails) so the caller can react synchronously.
- A separate `publish_dlq(topic: str, dlq_message: dict)` method, or one method with topic explicit — pick whichever reads cleaner.
- Delivery report callbacks update `kafka_publish_duration_seconds` and log success/failure.
- A `flush(timeout_s)` method for the entry point to call on shutdown.
- `tests/test_publisher.py` mocking the producer:
  - Successful publish returns / does not raise.
  - Failed delivery raises a clear exception so the caller (issue 0010) can route to retry/DLQ.
  - JSON serialisation is correct for nested dicts / UUIDs / timestamps.

## Out of scope

- Retry-on-failure orchestration — issue 0010 owns.
- Schema Registry / Avro / Protobuf — JSON only per PRD.
- Consumer code.

## Acceptance criteria

- Publisher constructible from broker config.
- Publishing blocks until delivery report is received and surfaces failures as exceptions.
- `tests/test_publisher.py` passes with the producer mocked.

## Notes

- **Ask before deciding** the sync semantics: per-message `produce()` + `flush()` (blocks per call, simpler, slower), or a delivery-report callback that signals completion (more efficient, more code). The "sync + threading" constraint from CLAUDE.md says favour the simpler path.
- Be careful with JSON serialisation of UUIDs / datetimes. **Ask** if a custom encoder vs. requiring callers to pre-serialise those types is the right boundary — affects who owns serialisation rules.
