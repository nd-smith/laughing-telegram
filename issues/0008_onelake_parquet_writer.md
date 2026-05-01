# 0008 — OneLake Parquet writer

## Goal

Buffer enveloped events in memory and flush them to OneLake as Parquet files on interval or size threshold. Per PRD §Pipeline Components §5.

## Scope

- `pipeline/writer.py` exposing a class (e.g., `OneLakeWriter`) that:
  - Accepts envelopes via `add(envelope: dict)`.
  - Flushes when the buffer hits the size threshold (default 1000) or the interval elapses (default 60s) — whichever comes first, per PRD §Scale & Performance.
  - Serialises with `pyarrow` to Parquet.
  - Writes via `azure-storage-file-datalake` using `DefaultAzureCredential`.
  - Path convention: `{lakehouse_path}/{source}/{year}/{month}/{day}/{timestamp}_{batch_id}.parquet`.
  - Updates metrics: `batch_write_duration_seconds`, `batch_size`, `buffer_size` (gauge updated on `add` and after flush).
  - Logs flush start / success / failure with batch size.
  - Exposes a `flush()` method for the entry point to call on shutdown to drain the buffer.
- `tests/test_writer.py` covering:
  - Size-triggered flush at threshold.
  - Interval-triggered flush after elapsed time (use a small interval in tests).
  - Path format matches the convention.
  - SDK errors surface to the caller (no internal swallowing — retry policy is owned by issue 0010).
  - `flush()` drains the buffer and resets state.

## Out of scope

- Delta Lake transactional writes — start with plain Parquet (PRD says "Parquet/Delta"). **Ask** if Delta is required before adding the dependency.
- Retry/backoff on write failure — issue 0010 owns retry policy at the pipeline level.
- Compaction / file-size optimisation.

## Acceptance criteria

- Writer constructible from `(lakehouse_path, source_name, flush_interval_s, flush_size, ...)`.
- All `tests/test_writer.py` cases pass with the ADLS SDK mocked.
- Path generation tested independently of the SDK.

## Notes

- **Ask before deciding** how interval-based flush is driven — background thread, explicit `tick()` called from the main loop, or `add()` checking elapsed time. Threading is the most "real-time" but adds locking concerns; explicit tick is simpler. Worth surfacing.
- **Ask before deciding** the pyarrow schema: structured (top-level envelope fields each as a column, `metadata` and `payload` as nested structs or JSON strings) vs. flat (one JSON-string column per envelope). Affects downstream readability of the Parquet files significantly.
- All locking/concurrency must be safe for the threading model from PRD §Scale & Performance.
