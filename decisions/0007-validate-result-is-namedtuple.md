# 0007 — `validate` returns a `NamedTuple` result

**Status:** Accepted
**Date:** 2026-05-01

## Context

Issue [0003](../issues/complete/0003_event_validation.md) adds `pipeline/validation.py` with a single `validate(raw_event, required_fields)` function. The function returns a pass/fail result with a human-readable `reason` on failure, suitable for both logging and DLQ payloads. The issue's Notes flagged the result shape as an "ask before deciding" item. Three options were considered:

- **Bare tuple `(ok: bool, reason: str | None)`.** Smallest mechanism, stdlib, but call sites unpack positionally and `reason` is implicit-by-position. A naive `if result:` is always truthy on a non-empty tuple, which is an easy misuse for a non-expert maintainer. Field meaning is hidden in the order.
- **`typing.NamedTuple`.** Same memory/representation as a tuple, plus named field access (`result.ok`, `result.reason`). Immutable, no `__init__` to write, stdlib only. Reads clearly at call sites without an extra concept to import beyond the function.
- **`dataclass`.** Also gives named fields, but adds mutability by default and slightly more ceremony for no gain — we never mutate a validation result, and we don't need its richer features here.

The repo's guiding principle is simplicity-first for non-expert maintainers and AI-assisted troubleshooting. ADR [0006](0006-build-envelope-keyword-only-signature.md) made the analogous choice for `build_envelope` — pick the stdlib option that names things at the call site, skip indirection that doesn't earn its place.

## Decision

`validate` returns a `typing.NamedTuple` named `ValidationResult` with two fields: `ok: bool` and `reason: str | None`. On success, `reason` is `None`; on failure, `reason` is a human-readable string suitable for inclusion in a log line or DLQ payload (e.g. naming the missing field).

## Consequences

- Call sites read as `result.ok` and `result.reason` — the meaning is explicit at the point of use.
- The result is immutable and tuple-compatible, so it can still be unpacked (`ok, reason = validate(...)`) if a caller prefers.
- No extra type concept beyond `typing.NamedTuple` — the module stays stdlib-only and matches the envelope module's posture.
- If the result ever needs additional fields (e.g. an error code) the `NamedTuple` extends cleanly; if it grows beyond a handful of fields, revisiting with a dataclass remains a low-cost refactor.
