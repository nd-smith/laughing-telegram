# Decision Index

- [How Claude works in this repo](0001-how-claude-works-in-this-repo.md) {2026-05-01} — working agreement: never guess, no placeholders, stay in scope, human in the loop
- [Use ADRs for design decisions](0002-use-adrs-for-design-decisions.md) {2026-05-01} — every option-3 pause produces an ADR; standard ADR format
- [Issues-driven workflow for pipeline code work](0003-issues-driven-workflow.md) {2026-05-01} — pipeline code work requires an issue file; meta/bootstrap work is exempt
- [Issue completion workflow](0004-issue-completion-workflow.md) {2026-05-01} — move completed issues to issues/complete/; strikethrough index entry with both dates and dev notes
- [Pin dependencies with exact versions](0005-pin-dependencies-with-exact-versions.md) {2026-05-01} — `requirements.txt` uses `==` for reproducible builds; deliberate manual bumps
- [`build_envelope` keyword-only signature](0006-build-envelope-keyword-only-signature.md) {2026-05-01} — nine caller inputs passed as kwargs; rejected positional and dataclass alternatives
- [`validate` returns a `NamedTuple` result](0007-validate-result-is-namedtuple.md) {2026-05-01} — `ValidationResult(ok, reason)` over bare tuple or dataclass
- [Source-loader test fixtures via in-memory `sys.modules`](0008-source-loader-test-fixtures-via-sys-modules.md) {2026-05-02} — fake source modules constructed in tests, no on-disk fixture tree
- [Log context via `contextvars`](0009-log-context-via-contextvars.md) {2026-05-02} — `log_context` context manager + filter-stamped record attrs; rejected `LoggerAdapter` and per-call `extra=`
- [Custom JSON formatter, no `python-json-logger` dependency](0010-custom-json-formatter-no-dependency.md) {2026-05-02} — small `Formatter` subclass with `json.dumps(default=str)`; no new requirement
- [Event Hub consumer callback shape: single-event](0011-consumer-callback-shape-single-event.md) {2026-05-02} — `callback(event)` per non-`None` event; checkpoint after success, log+continue on raise
- [Event Hub consumer shutdown driven by entry-point flag](0012-consumer-shutdown-driven-by-entry-point-flag.md) {2026-05-02} — `run(callback, shutdown: Event)`; watcher thread closes client on flag set
- [OneLake writer interval flush via background thread](0013-writer-interval-flush-via-background-thread.md) {2026-05-02} — daemon flusher thread + buffer lock; rejected `add()`-time check and entry-point `tick()`
- [Parquet schema: flat envelope columns plus JSON metadata/payload](0014-parquet-schema-flat-columns-plus-json.md) {2026-05-02} — top-level fields as typed columns; `metadata` and `payload` as JSON strings
- [Kafka publisher sync semantics: per-message produce + flush](0015-kafka-publisher-sync-via-produce-flush.md) {2026-05-02} — `publish()` does `produce()` then `flush(timeout)`; rejected delivery-report Event signalling
- [Kafka publisher: strict JSON serialisation, callers own type conversion](0016-kafka-publisher-strict-json-serialisation.md) {2026-05-02} — `json.dumps(envelope)` with no `default=`; envelope.py owns UUID/datetime stringification
