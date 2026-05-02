# 0009 — Log context via `contextvars`

**Status:** Accepted
**Date:** 2026-05-02

## Context

Issue [0005](../issues/complete/0005_structured_json_logging.md) requires every emitted log line to include `source`, `correlation_id`, and `envelope_id`. `source` is fixed at worker startup (one process per source per the PRD) and can be baked into the formatter. `correlation_id` and `envelope_id` are per-event values that come into existence partway through processing — `correlation_id` after the raw event is parsed, `envelope_id` once the envelope is built — and must propagate to every log line emitted within that event's processing scope without each call site having to thread them through.

The issue's Notes flagged the propagation mechanism as an "ask before deciding" item. Three options were considered:

- **`contextvars.ContextVar` + a `log_context` context manager.** A small wrapper sets the context vars on enter, resets via the token on exit. A `logging.Filter` (or formatter step) reads the current values when a record is emitted and attaches them. Call sites stay clean — `log.info("...")` works once context is set, with no per-call ceremony. `contextvars` are per-thread under threading (each thread gets its own copy of the context), which matches the project's "sync + threading, not asyncio" constraint, and they remain correct if any future code path uses asyncio.
- **`logging.LoggerAdapter`.** Stdlib, simple in isolation. But the adapter has to be created per event and threaded through every function that logs, or a new adapter has to be constructed at each call site from the current event's IDs. That's exactly the call-site noise the issue is trying to avoid, and it makes the "logger" concept ambiguous (module logger vs. event-scoped adapter).
- **Explicit `extra=` at every call site.** Zero infrastructure, but every `log.info(...)` has to remember to pass `extra={"correlation_id": ..., "envelope_id": ...}`. Easy to forget, noisy, and defeats the point of a centralised logger.

The repo's guiding principle is simplicity-first for non-expert maintainers and AI-assisted troubleshooting. `contextvars` adds a small one-time piece of infrastructure (a few lines in `shared/logging.py`) and removes ceremony from every call site forever after — the right side of the simplicity trade-off.

## Decision

`shared/logging.py` defines two module-level `ContextVar`s, `_correlation_id` and `_envelope_id`, both defaulting to `None`. A context manager `log_context(*, correlation_id=None, envelope_id=None)` sets the supplied values on enter and resets them on exit using the token returned by `ContextVar.set()`. A `logging.Filter` attached to the root handler reads the current values on each emitted record and stamps them onto the record so the JSON formatter can serialise them. `source` is captured at `setup_logging(source, level)` time and held on the formatter.

Per-event scope at the worker is a single `with log_context(correlation_id=..., envelope_id=...):` block around envelope construction and downstream steps. Within the block, every `log.info(...)` / `log.error(...)` automatically picks up the current IDs; outside the block they reset to `None` and the JSON line records them as `null`.

## Consequences

- Call sites stay terse — module-level loggers (`log = logging.getLogger(__name__)`) work everywhere with no adapter or `extra=` boilerplate.
- Context is correct under threading: each thread gets its own copy of the context vars, so concurrent event processing in different threads cannot leak IDs across each other.
- Correctness depends on always entering `log_context` for an event and always exiting it — the context-manager form (vs. raw `set`/`reset` calls) makes this hard to get wrong, and tests cover scope clearing.
- Forgetting to wrap an event scope in `log_context` is a silent failure mode: logs emit with `null` IDs instead of the event's real IDs. This is mitigated by having one obvious place in the worker main loop where the `with` block lives, and by the formatter still emitting the keys (just as `null`) so the omission is visible in the output.
- Adopting `contextvars` does not preclude callers from also passing `extra=` for one-off structured fields — the formatter merges both.
