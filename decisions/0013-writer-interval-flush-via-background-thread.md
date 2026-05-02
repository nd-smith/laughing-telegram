---
name: 0013 — OneLake writer interval flush via background thread
description: Writer owns a daemon flusher thread plus a buffer lock; rejected add()-time elapsed-check and entry-point tick()
type: project
---

# 0013 — OneLake writer interval flush via background thread

**Status:** Accepted
**Date:** 2026-05-02

## Context

Issue [0008](../issues/0008_onelake_parquet_writer.md) adds `pipeline/writer.py`. PRD §Scale & Performance specifies a 60-second interval flush "or 1000 events, whichever comes first". The size trigger is straightforward — `add()` checks buffer length. The interval trigger has no obvious owner: the consumer (ADR [0011](0011-consumer-callback-shape-single-event.md), ADR [0012](0012-consumer-shutdown-driven-by-entry-point-flag.md)) blocks the worker's main thread inside `EventHubConsumerClient.receive(...)` and only surfaces control flow on event arrival via the per-event callback. There is no natural tick point for the writer to piggy-back on.

Three options were considered:

- **Background flusher thread inside the writer.** A daemon thread sleeps on the configured interval and flushes if the buffer is non-empty. Buffer access is protected by a `threading.Lock` because `add()` is called from the consumer callback thread and `flush()` is called from both the flusher thread and (on shutdown) the entry point. Real-time: idle buffers still flush on schedule even when events stop arriving.
- **`add()` checks elapsed time.** Simplest mechanically: no thread, no lock, the next `add()` triggers a flush if enough time has passed. Fails the moment events stop arriving — the last batch of a quiet day sits in memory until shutdown, missing OneLake's 60-second freshness expectation.
- **Explicit `tick()` from the entry point.** Pushes the timing concern out of the writer, but the entry point has no main loop of its own — `receive()` is blocking — so it would have to spawn a separate ticker thread anyway, just relocating option A's complexity to a less-obvious place.

PRD §Scale & Performance treats the 60-second interval as a freshness contract, not an opportunistic best-effort, which rules out option B. Option C only seems simpler until you notice the entry point has nowhere to put the tick. Option A puts the timing concern in the one place that owns the buffer it operates on.

## Decision

`OneLakeWriter` owns a daemon `threading.Thread` (started on construction, stopped via `stop()` which sets an internal `threading.Event` and joins). The thread loop is `while not stop_event.is_set(): stop_event.wait(flush_interval_s); flush()` — using the event's wait-with-timeout means shutdown returns control immediately rather than waiting out the full interval. A single `threading.Lock` guards the buffer; `add()` and `flush()` each acquire it for as briefly as possible (append in `add()`; swap-and-clear in `flush()`, then release the lock before performing the actual SDK upload of the captured snapshot). `flush()` is also exposed publicly so the entry point can drain the buffer on shutdown after the consumer has stopped delivering events.

## Consequences

- The writer is self-contained: timing, locking, and SDK I/O all live in one file with one obvious shutdown path.
- The flusher thread is one extra moving part inside the writer, justified by the SDK's blocking-`receive` shape upstream and the freshness contract from the PRD.
- Holding the lock only across the buffer swap (not across the SDK upload) means a slow upload does not block `add()` from accepting new events, which matters under load.
- `flush()` is reentrant-safe: the swap-and-clear empties the buffer atomically, so two simultaneous flushes (e.g., size-trigger from `add()` racing with the interval thread) cannot double-write the same envelopes — at worst one of them flushes an empty list and is a no-op.
- Tests drive the interval branch with a small `flush_interval_s` (a few tens of ms) and assert the SDK mock saw an upload; they drive the size branch by passing `flush_size=N` and calling `add()` `N` times without starting the thread.
- Forgetting to call `stop()` in the entry point is a hang-on-shutdown failure mode (daemon thread keeps the worker alive); mitigated by a single explicit shutdown sequence in the entry point (issue 0011).
