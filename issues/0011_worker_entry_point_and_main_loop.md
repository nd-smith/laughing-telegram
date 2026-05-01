# 0011 — Worker entry point & main loop

## Goal

Wire every component together behind a `python -m pipeline --source <name>` CLI with graceful shutdown. Per PRD §Pipeline Components §1.

## Scope

- `pipeline/__main__.py` that:
  - Parses `--source <source-name>` (required).
  - Reads pipeline configuration from environment variables (pipeline_id, lakehouse path, Event Hub namespace overrides if any, Kafka broker list, metrics port, checkpoint store URL, etc.). The accepted env vars are documented as a top-of-file docstring.
  - Calls `setup_logging(source=...)` from issue 0005.
  - Calls `start_metrics_server(port=...)` from issue 0006.
  - Calls `load_source(name)` from issue 0004.
  - Constructs `EventHubConsumer` (0007), `OneLakeWriter` (0008), `KafkaPublisher` (0009), and the processor (0010), passing the loaded source.
  - Runs the consumer's main loop, handing each event to the processor.
  - Installs SIGTERM/SIGINT handlers that:
    1. Stop the consumer from pulling new events.
    2. Drain the writer buffer (`writer.flush()`).
    3. Flush the Kafka producer (`publisher.flush(...)`).
    4. Exit cleanly.
- `tests/test_main.py` smoke-testing:
  - `--help` runs and exits 0.
  - `--source` missing exits with a clear error.
  - `--source nonexistent` exits with a clear error referencing `load_source`.
  - With all components mocked, signal handler invocation triggers writer flush and producer flush in order.

## Out of scope

- Real end-to-end run against live Event Hub / OneLake / Kafka.
- Config schema enforcement libraries — direct env reads with explicit `KeyError`-style messages are sufficient.
- Health endpoints beyond the metrics scrape endpoint.

## Acceptance criteria

- `python -m pipeline --help` shows usage.
- `python -m pipeline --source nonexistent` exits non-zero with a clear error.
- All tests in `tests/test_main.py` pass with components mocked.
- All previously written component tests still pass.

## Notes

- **Ask before deciding** signal-handling specifics if threading interactions get tricky — Python signal handlers run in the main thread, which interacts with how the consumer and writer threads (if any) are structured.
- Env-var names should be consistent (suggest `PROPGATEWAY_*` prefix). Document them in the module docstring; the docstring is the spec.
- This is the final wiring issue — verify the full unit-test suite passes after merging this.
