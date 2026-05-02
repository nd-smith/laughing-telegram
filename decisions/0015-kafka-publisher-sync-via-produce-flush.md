---
name: 0015 — Kafka publisher sync semantics: per-message produce + flush
description: KafkaPublisher.publish blocks via produce() then flush(timeout); rejected delivery-report Event signalling for being more code without payoff at PRD throughput
type: project
---

# 0015 — Kafka publisher sync semantics: per-message produce + flush

**Status:** Accepted
**Date:** 2026-05-02

## Context

Issue [0009](../issues/0009_kafka_publisher.md) adds `pipeline/publisher.py` wrapping `confluent_kafka.Producer`. The PRD requires the publisher to surface delivery failures synchronously to its caller (issue 0010 owns retry/DLQ). `confluent_kafka.Producer` is async by design: `produce()` queues a message and returns immediately; delivery is signalled later by a callback fired during `poll()` or `flush()`. Two ways to bolt sync semantics onto that shape were considered:

- **Per-message `produce()` + `flush(timeout)`.** Each `publish()` call queues exactly one message and then calls `flush(timeout)`, which blocks until all queued messages report and fires their `on_delivery` callbacks. The callback closes over a small mutable dict to record success or the error; after `flush()` returns, `publish()` checks the dict and either returns or raises `PublishError`. Trivial to read; no shared state across calls; `flush()` doubles as the "drain on shutdown" entry point. Cost: each call drains the producer queue, so if anything else were enqueued in parallel it would also be waited on. At the PRD's "thousands of events per minute per source" throughput on a single sync worker thread, that cost is well below the per-event budget.
- **Delivery-report callback signals completion via `threading.Event`.** Each `publish()` queues a message with a closure that sets a per-call `Event` and stashes the error; `publish()` then loops `producer.poll(timeout)` until the Event fires (or the deadline passes). Avoids draining the producer queue on every call, which matters at much higher throughput. Costs: more moving parts (per-call Event, deadline arithmetic, the explicit poll loop), more failure modes (poll returning 0 with the Event still unset), and a callback that runs on the producer's internal thread mutating per-call state — additional reasoning load for non-expert maintainers.

CLAUDE.md's "simplicity first" and "favour the simpler path" tip the balance. The per-message produce+flush pattern is small enough to read in one screen; the throughput PRD targets are a small fraction of what `confluent_kafka` handles even with this naive shape; and `flush(timeout)` already gives us the shutdown entry point the issue asks for.

## Decision

`KafkaPublisher.publish(topic, envelope)` queues exactly one message via `producer.produce(topic, value=payload, on_delivery=cb)` and then calls `producer.flush(self._flush_timeout_s)`. The `on_delivery` callback closes over a dict (`{"err": None, "done": False}`), records `kafka_publish_duration_seconds` from a `time.monotonic()` baseline captured before `produce()`, logs success or failure, and stashes the broker error if any. After `flush()` returns:

- `flush()` returned non-zero, or `done` is still `False` → raise `PublishError("...did not complete within Ns")`.
- `err` is set → raise `PublishError("...failed: <error>")`.
- Otherwise return.

`KafkaPublisher.flush(timeout_s)` is a thin pass-through to `producer.flush(timeout_s)` for the entry point's shutdown path. No background threads. No long-lived per-publisher state beyond the producer handle.

## Consequences

- The hot path is six lines and reads top-to-bottom. A non-expert maintainer reading `publish()` sees the produce, the flush, the error checks, and the raise. Nothing happens "later".
- Per-call latency is bounded by the broker round-trip plus the producer's internal batching window — fine at the PRD throughput; a single worker thread serialises publishes anyway.
- `flush(timeout_s)` gives the entry point exactly the shutdown primitive issue 0011 needs, with no extra surface to learn.
- `PublishError` (a single concrete exception type) is what issue 0010 catches to drive retry/DLQ. Both delivery failure and flush timeout map to the same class because the retry policy is identical for both — the pipeline cannot tell them apart in any actionable way.
- If a future issue raises throughput targets by an order of magnitude or more, the publisher can be re-shaped to delivery-report-Event signalling without changing its public surface (`publish` / `flush` stay the same). This decision is reversible at that point.
- Concurrent publishers in the same process (not currently planned) would each see `flush()` wait on every queued message, not only their own. Acceptable because the worker is single-threaded for processing per PRD §Concurrency model; revisit if that changes.
