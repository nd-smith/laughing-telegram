# 0020 — Source contract extends with `REQUIRED_FIELDS`

**Status:** Accepted
**Date:** 2026-05-02

## Context

Issue [0011](../issues/complete/0011_worker_entry_point_and_main_loop.md) wires the worker entry point and constructs `Processor` from issue 0010. `Processor.__init__` takes `required_fields: Iterable[str]` (forwarded into `pipeline.validation.validate`), but the source-module contract from issue [0004](../issues/complete/0004_source_module_contract_and_loader.md) only mandates `SOURCE_NAME`, `EVENT_HUB_NAMESPACE`, `EVENT_HUB_NAME`, `KAFKA_OUTPUT_TOPIC`, and `extract`. The entry point therefore had no canonical place to read required-field names from.

Four options were on the table:

- **(a) Extend the source contract** — every source module exports `REQUIRED_FIELDS: tuple[str, ...]` (possibly `()`); the loader validates type alongside the existing checks.
- **(b) Optional source attribute** — `getattr(module, "REQUIRED_FIELDS", ())` with no contract change.
- **(c) Env var** — `PROPGATEWAY_REQUIRED_FIELDS=field1,field2` read once at startup.
- **(d) Hardcode `()`** — let the extractor's `KeyError` on missing fields land in the retry/DLQ flow.

PRD §3 puts validation before the per-source extractor and treats "expected top-level fields (per source extractor requirements)" as a validation concern. That places the required-field list with the source, not with deployment config. Options (c) and (d) split that concern away from the source code, making it harder to reason about a source's contract from its module file. (b) and (a) keep it co-located, but (b) lets a typo (`REQUIREDFIELDS = ("data",)`) silently degrade to "no validation"; (a) makes the omission a hard load-time failure with a named attribute.

## Decision

The source-module contract gains a fifth required export, `REQUIRED_FIELDS: tuple[str, ...]`, alongside the existing four string constants and `extract`. `pipeline.sources.load_source` enforces:

- presence of the attribute (`TypeError` naming the attribute when missing),
- outer type is `tuple` (`TypeError` naming the attribute and the actual type when not),
- every element is a `str` (`TypeError` naming the attribute, the offending index, and the element's type).

An empty tuple `()` is valid and means "no required fields beyond being a dict". The entry point passes `source_module.REQUIRED_FIELDS` straight into `Processor(required_fields=...)`.

## Consequences

- The required-fields list lives in the same file as the extractor that uses those fields, which is the right neighborhood for AI-assisted maintenance.
- One extra line per source module, plus the same line in test fixtures. Existing source-loader tests grew three cases (missing attr; wrong outer type; wrong element type) — symmetric with how the existing string-attribute validation is tested.
- A source that wants to skip validation must explicitly write `REQUIRED_FIELDS = ()`, which is a deliberate, visible choice.
- The contract is now five exports, one more than the original PRD example. That is acceptable: the PRD's example source module is illustrative, not exhaustive, and the gain in determinism (validation always runs against a known list) outweighs the small complexity bump.
