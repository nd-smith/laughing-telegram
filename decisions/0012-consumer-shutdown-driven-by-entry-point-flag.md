# 0012 — Event Hub consumer shutdown driven by entry-point flag

**Status:** Accepted
**Date:** 2026-05-02

## Context

Issue [0007](../issues/complete/0007_event_hub_consumer.md) adds `pipeline/consumer.py`. The sync `EventHubConsumerClient.receive(on_event=...)` blocks the calling thread until `client.close()` is called from elsewhere — there is no built-in stop flag. PRD §Pipeline Components §1 places SIGTERM/SIGINT handling in the worker entry point (issue 0011). The consumer therefore needs some contract for "the worker has decided to shut down; please stop." The issue's Notes asked us to surface the trade-off rather than pick silently. Two options were considered:

- **Shutdown owned by the consumer's run loop.** The consumer installs its own signal handlers (or exposes a synchronous `stop()` method that the entry point wires up). Self-contained from the consumer's perspective, but it splits responsibility for process-wide concerns: signal handling is now in two places (the consumer and any other long-running component the worker spawns), and the consumer has to know about K8s `SIGTERM` semantics. Awkward for tests too — patching out signal handlers per test.
- **Shutdown driven by a flag from the entry point.** The entry point owns SIGTERM/SIGINT handlers (one place, one policy), sets a `threading.Event` when a signal arrives, and passes that event into `consumer.run(callback, shutdown)`. The consumer is responsible only for translating "flag set" into "stop receiving" by closing the underlying client.

The project's guiding principle is simplicity-first with a single, obvious place for each concern. Centralising signal handling in the entry point — which already exists for that purpose per the PRD — keeps the consumer a thin SDK wrapper and matches how a future writer/publisher long-running thread would also receive the same flag.

## Decision

`EventHubConsumer.run(callback, shutdown: threading.Event)` accepts a shutdown event from the caller. The entry point (issue 0011) installs SIGTERM/SIGINT handlers, sets the flag when triggered, and is the only place process-wide signal handling lives. Inside `run()`, the consumer spawns a small daemon watcher thread that does `shutdown.wait()` and then calls `self._client.close()`, which causes `receive()` to return. The watcher is joined before `run()` returns; if `receive()` exits for any other reason, `run()` sets the flag itself so the watcher exits and is joined cleanly. A separate `EventHubConsumer.close()` method is exposed for callers (and tests) that want to close the client directly.

## Consequences

- One owner for signal handling — the worker entry point — matches the PRD and avoids ambiguous behaviour if multiple components installed handlers.
- The consumer stays a thin SDK wrapper: no signal module, no global state. Tests drive shutdown by setting the flag on a `threading.Event`, no signal mocking needed.
- The watcher thread is one extra moving part inside the consumer, justified by the SDK's blocking-`receive` shape — there is no SDK-native stop flag to use instead.
- Forgetting to set the shutdown flag in the entry point is a hang-on-shutdown failure mode; mitigated by a single place in the worker main loop where the flag is wired and by the explicit `close()` escape hatch.
- The same pattern (accept a `threading.Event`, watch it, close on signal) extends naturally to other long-running components added by later issues, so there is one shutdown idiom across the worker.
