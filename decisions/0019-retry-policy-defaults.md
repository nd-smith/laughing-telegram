---
name: 0019 — Retry policy defaults: 3 retries, exponential backoff base 1s, injectable sleep
description: Processor retries up to 3 times after first failure with sleeps of 1s/2s/4s; max_retries and backoff_base_s configurable; sleep injected so tests run instantaneously
type: project
---

# 0019 — Retry policy defaults: 3 retries, exponential backoff base 1s, injectable sleep

**Status:** Accepted
**Date:** 2026-05-02

## Context

Issue [0010](../issues/complete/0010_processing_pipeline_and_retry_dlq.md) implements the retry-then-DLQ flow. PRD §Error Handling §Retry Strategy says: "retry up to **3 times** with exponential backoff" and "`pipeline.retry_count` in the envelope tracks attempts" — but it does not specify the backoff base or whether "3 times" includes the initial attempt. The issue called out three specifics to resolve before coding:

- **Number of attempts.** Reading the PRD literally, "retry up to 3 times" reads as 3 retries *after* the first attempt — so up to 4 total attempts. The natural English usage of "retry" excludes the initial try.
- **Backoff base.** PRD says "exponential backoff" but not the base. The issue's own draft proposes 1s doubling (1s, 2s, 4s). Within typical retry conventions for I/O-bound work this is a standard starting point — long enough to ride out a transient network/broker hiccup, short enough that exhausting the retries does not block per-event processing for more than ~7s of wall time.
- **Test ergonomics.** Real `time.sleep(1)`/`(2)`/`(4)` would make the test suite take ~7 seconds per worst-case test, with several such tests. Tests need a way to skip the sleep without disabling the retry/backoff logic itself.

## Decision

- `max_retries` defaults to **3**. The processor makes up to `max_retries + 1 = 4` total attempts before the DLQ.
- `backoff_base_s` defaults to **1.0**. Sleep before retry `n` (0-indexed) is `backoff_base_s * (2 ** n)`, giving the default sequence **1s, 2s, 4s** for the three retries.
- `sleep` is injected as a constructor argument, defaulting to `time.sleep`. Tests pass a list-append closure (or any zero-cost callable) to assert on the requested durations without waiting.
- `pipeline.retry_count` in the envelope equals the attempt index, so the envelopes the writer/publisher see across attempts carry `retry_count = 0, 1, 2, 3`. The DLQ payload's `retry_count` equals `max_retries` on exhaustion (matching the PRD bullet "Retry count" — the number of retries that happened).
- All three of `max_retries`, `backoff_base_s`, and `sleep` are constructor keyword arguments, so ops can tune them per source without code changes and tests can drive backoff timing assertions directly.

## Consequences

- A run that exhausts retries spends roughly `1 + 2 + 4 = 7s` of wall time in `sleep` plus the I/O of four attempts. Acceptable at PRD throughput targets (thousands of events per minute per source) because failures are the exception, not the norm; a worker that is failing this often is the alerting case, not the steady-state case.
- Tests configure `backoff_base_s=0.0` (or pass a no-op `sleep`) to keep the suite fast. The retry/backoff *logic* is exercised; only the wall-clock wait is skipped.
- Operations can raise `max_retries` or change the base without code review of the processor itself, by passing different values at construction time. If a source needs a different policy, the entry point (issue 0011) decides.
- The retry semantics re-run the entire 5-step flow (validate → extract → envelope → write → publish), not just the failing step. The writer can therefore see multiple envelopes for a single source event, each with a distinct `envelope_id` and increasing `retry_count`. This duplication is accepted per the issue's literal flow specification; downstream OneLake consumers can dedupe by correlation_id if they need exactly-once semantics. ADR 0017 records the corresponding class shape that owns this loop.
