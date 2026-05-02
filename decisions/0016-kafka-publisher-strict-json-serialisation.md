---
name: 0016 — Kafka publisher: strict JSON serialisation, callers own type conversion
description: KafkaPublisher calls json.dumps without a default= handler; envelope.py owns UUID/datetime stringification; rejected default=str catch-all to keep type ownership at the construction boundary
type: project
---

# 0016 — Kafka publisher: strict JSON serialisation, callers own type conversion

**Status:** Accepted
**Date:** 2026-05-02

## Context

Issue [0009](../issues/0009_kafka_publisher.md) needs the publisher to JSON-serialise the envelope before handing bytes to `confluent_kafka.Producer.produce(value=...)`. The envelope (PRD §Envelope Schema) contains fields that are not natively JSON-serialisable in Python — UUIDs, datetimes — unless they have already been converted to strings by the time they reach the publisher. Two boundaries were considered for that conversion:

- **Strict in the publisher; envelope construction owns type conversion.** `publish` calls `json.dumps(envelope)` with no `default=` handler. If the dict contains a `UUID` or a `datetime`, `json.dumps` raises `TypeError` immediately. The publisher's contract is "give me a dict whose leaves are JSON-native." `pipeline/envelope.py` already produces such a dict (its tests fix `envelope_id` as a string and timestamps as ISO8601 strings).
- **Forgiving in the publisher; `default=str` catch-all.** Mirrors `pipeline/writer.py`, which does `json.dumps(env.get("metadata"), default=str)` and `json.dumps(env.get("payload"), default=str)` (writer.py:214–215). Anything not natively serialisable becomes `str(value)`, which works for UUIDs and datetimes today and silently produces something for anything else.

The two cases are different: `writer.py` uses `default=str` for `metadata` and `payload` because those are *user-shaped* — per-source extractors and raw upstream payloads can hand the pipeline anything. The pipeline must not crash on a payload it has no control over. The publisher's input, by contrast, is a fully-constructed envelope from `envelope.py` — pipeline-controlled. There is one place where a UUID could leak through (envelope construction), and being strict at the publisher surfaces that bug at the boundary instead of papering over it. CLAUDE.md's "no defensive layers" and "fail fast" preferences apply.

## Decision

`KafkaPublisher.publish(topic, envelope)` calls `json.dumps(envelope).encode("utf-8")` with no encoder customisation. A non-JSON-native value in the envelope raises `TypeError` from `json.dumps` directly — the publisher does not catch and rewrap it; the `TypeError` is the diagnostic. `pipeline/envelope.py` is the canonical owner of UUID-to-str and datetime-to-ISO8601 conversion; any new envelope field that is not natively serialisable must be converted there before reaching downstream components.

The asymmetry with `writer.py` is deliberate: `writer.py` wraps `metadata` and `payload` (variable, externally-shaped) with `default=str`; the publisher serialises the whole envelope (fixed, pipeline-shaped) strictly. `metadata` and `payload` survive that strict pass because they were already JSON-string-ified there… wait — they are not stringified for the publisher. The publisher serialises the *whole envelope as a dict tree*, so `metadata` and `payload` go through `json.dumps` as nested dicts. That is fine: their leaves are whatever the source extractor produced (strings, ints, lists, dicts, booleans, None) plus the raw upstream payload, which is already JSON because it came off Event Hub as JSON. If a source extractor were to put a non-JSON-native value into `metadata` (e.g. a `datetime`), that is a bug in the extractor and the strict publisher will surface it; the writer's `default=str` would have hidden it.

## Consequences

- Bugs in envelope construction or in source extractors that introduce non-JSON-native types fail loudly at publish time, with a `TypeError` naming the offending type. No silent string coercion.
- The publisher stays trivially small — `json.dumps(envelope).encode("utf-8")` is the entire serialisation step, no encoder class.
- The contract for `envelope.py` is now explicit: every value in the dict it returns is JSON-native. Future envelope changes (new fields, new metadata shapes from new sources) must hold this invariant.
- Tests for the publisher cover JSON correctness for nested dicts, nullable fields, and pre-stringified UUIDs/timestamps — i.e. the shape `envelope.py` actually produces — rather than asserting the publisher tolerates raw `UUID`/`datetime` objects.
- The asymmetry with `writer.py` is documented in this ADR and in module docstrings; non-expert maintainers reading both files need to understand *why* one uses `default=str` and the other does not.
- Reversible cheaply: switching to `default=str` is a one-line change if a future requirement makes strict serialisation onerous.
