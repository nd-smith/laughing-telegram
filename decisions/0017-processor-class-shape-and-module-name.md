---
name: 0017 — Processor class shape and module name
description: Per-event processor is a Processor class in pipeline/processor.py; rejected free function with kwargs and pipeline/process.py module name
type: project
---

# 0017 — Processor class shape and module name

**Status:** Accepted
**Date:** 2026-05-02

## Context

Issue [0010](../issues/complete/0010_processing_pipeline_and_retry_dlq.md) introduces the per-event glue between the pure components (validate, source extractor, build_envelope) and the I/O components (writer, publisher), wrapped in retry/DLQ orchestration. The issue's Notes flagged two related shape questions as "ask before deciding":

- **Function vs. class.** A free function would take ~12 dependencies as keyword arguments at every call site (source name, source event hub, pipeline_id, extractor callable, required_fields, writer, publisher, kafka topic, max_retries, backoff_base_s, sleep). Per-event call sites would either re-pass all of them or use a `functools.partial` to bind the setup-once subset. A class captures the setup-once state in `__init__` and exposes a single `process(raw_event, received_at)` method, mirroring the wiring style already chosen for `KafkaPublisher` (issue 0009), `OneLakeWriter` (issue 0008), and `EventHubConsumer` (issue 0007). Consistency with those siblings means a maintainer who has read one understands all four.
- **Module name.** The issue's draft name was `pipeline/process.py`. `process` collides with `multiprocessing.Process` in readers' minds — "is this about subprocess management?" — and the class itself reads better as `Processor` than as `Process` (which would shadow the stdlib name on import). `pipeline/processor.py` matches the noun form used elsewhere (`publisher.py`, `consumer.py`, `writer.py`).

## Decision

The per-event glue is a class `Processor` in `pipeline/processor.py`. Setup-once state — source identity, dependencies (writer, publisher, extractor), policy parameters (max_retries, backoff_base_s, sleep) — is captured in `__init__` as keyword-only arguments. Per-event invocation is `processor.process(raw_event, received_at)`.

## Consequences

- The processor's wiring posture matches its three I/O siblings; a reader who has seen `KafkaPublisher.__init__` already knows what to expect.
- Per-event call sites stay short (`processor.process(event, received_at)`) — the entry-point loop in issue 0011 does not need to thread setup state through the per-event path.
- `Processor` as the type name avoids confusion with `multiprocessing.Process`. The module name `processor.py` mirrors the noun form already used for `publisher.py`, `consumer.py`, `writer.py`.
- If the per-event code ever needs to be called from a context that does not warrant constructing a class (e.g., a one-off script reprocessing a single event), it remains trivial to add a thin module-level helper that builds a `Processor` and calls `process`.
