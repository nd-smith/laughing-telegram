# 0010 — Custom JSON formatter, no `python-json-logger` dependency

**Status:** Accepted
**Date:** 2026-05-02

## Context

Issue [0005](../issues/complete/0005_structured_json_logging.md) requires every log line to be a single JSON object on stdout, with a fixed schema: `timestamp` (ISO8601 UTC), `level`, `source`, `correlation_id`, `envelope_id`, `message`, plus any caller-supplied structured extras. K8s collects from stdout — there is no file rotation, no log shipper, no exotic formatting requirement.

The issue's Notes flagged the implementation choice as an "ask before deciding" item. Two options were considered:

- **`python-json-logger` dependency.** A maintained third-party formatter that handles JSON serialisation, field renaming, and reserved-attribute filtering. Adds one dependency to `requirements.txt`, plus the cognitive cost of a new library configured through its own API. Offers more knobs than this project needs.
- **Custom `logging.Formatter` subclass.** A small `JsonFormatter` whose `format()` method builds a dict from the record and `json.dumps()`-es it. The whole class is roughly 25 lines: pull the timestamp from `record.created`, the level/message from the record, the contextual IDs from the filter-stamped attributes, the source from a constructor-bound field, and merge any `extra=` keys that the stdlib `LogRecord` carries on attributes outside the reserved set.

The schema is small, fixed, and unlikely to grow. The project pins dependencies (ADR [0005](0005-pin-dependencies-with-exact-versions.md)) and treats each new dep as a maintenance cost; adding one for what is effectively a single `json.dumps` call would not earn its place. A custom formatter is also a more legible artefact for the AI-assisted-maintenance posture: the entire log line shape lives in one obvious file in this repo, with no library-version variance to reason about.

## Decision

`shared/logging.py` defines a `JsonFormatter(logging.Formatter)` that constructs a dict per record with the fixed schema fields and serialises it via `json.dumps(..., default=str)` to handle non-JSON-native values defensively. `setup_logging(source, level)` instantiates the formatter with the worker's source name, attaches a `StreamHandler(sys.stdout)` to the root logger, and attaches a context-reading `Filter` that stamps `correlation_id` and `envelope_id` onto each record from the contextvars established in ADR [0009](0009-log-context-via-contextvars.md). No new entry in `requirements.txt`.

## Consequences

- The complete log-line shape is visible in one file with no external indirection — easy to read, easy to grep, easy for Claude to reason about during troubleshooting.
- Zero new dependencies; reproducibility posture from ADR [0005](0005-pin-dependencies-with-exact-versions.md) is unchanged.
- If a future need genuinely requires capabilities `python-json-logger` provides (e.g., elaborate field renaming for an external sink contract), the formatter can be replaced module-locally without touching call sites.
- The formatter is responsible for tolerating values stdlib JSON cannot serialise. Using `default=str` keeps a stray non-serialisable extra from breaking logging entirely; the value reads as its `str()` repr in the line. Tests cover the common shapes; exotic types should be passed pre-serialised.
- The reserved-attribute set on `LogRecord` is documented but stdlib does not export it as a constant — the formatter hard-codes the small list it needs to skip when extracting `extra=` keys, which is fine for a fixed Python version pinned in `requirements.txt` but is the one place where a Python upgrade could surface a new attribute name to handle.
