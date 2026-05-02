---
name: 0014 — Parquet schema: flat envelope columns plus JSON metadata/payload
description: Top-level envelope fields become typed Parquet columns; metadata and payload stored as JSON strings; rejected single-JSON-column and fully-nested-struct schemas
type: project
---

# 0014 — Parquet schema: flat envelope columns plus JSON metadata/payload

**Status:** Accepted
**Date:** 2026-05-02

## Context

Issue [0008](../issues/0008_onelake_parquet_writer.md) writes enveloped events to OneLake as Parquet via `pyarrow`. The envelope has a fixed shape (PRD §Envelope Schema) with two parts that vary per source: `metadata` (per-source fields, defined by the source's extractor) and `payload` (the original raw event, which is the source system's own schema). Three Parquet schema shapes were considered:

- **Single-JSON-column.** One `envelope_json` string column. Schema never changes, write logic is trivial, fully lossless. Awful to query — every Fabric Lakehouse consumer parses JSON for every row, defeating most of the value of writing Parquet in the first place. Predicate pushdown, column pruning, and partition discovery on common fields (envelope_id, correlation_id, source.system, event.type, retry_count) all become full-table scans.
- **Flat top-level columns + JSON for `metadata` and `payload`.** All envelope fields outside `metadata` and `payload` become first-class typed Parquet columns: `envelope_id`, `correlation_id`, `schema_version`, `source_system`, `source_event_hub`, `source_original_timestamp`, `event_type`, `event_received_at`, `event_processed_at`, `pipeline_id`, `retry_count`, `processing_ms`. `metadata` and `payload` are stored as JSON strings (`metadata_json`, `payload_json`). The fixed envelope shell gets the column-store benefits; the variable parts side-step schema drift.
- **Fully nested with `metadata` as a Parquet struct.** Best query ergonomics on metadata fields too, but each source's metadata shape is defined by its extractor and may evolve. Mismatched shapes across batches (or across sources writing to the same table) break Parquet schema merge. Out of step with "simplicity first" — recovering from a schema drift would be far more painful than parsing a JSON string at query time.

The middle option gets the column-store benefits where they matter (the fixed envelope shell, which is what most queries filter on) and avoids the failure mode that kills option C (per-source schema drift). The PRD path convention already partitions by source — `{lakehouse_path}/{source}/...` — so cross-source metadata schema unification is not even needed for typical queries.

## Decision

The pyarrow schema is a flat list of top-level columns. Field-by-field mapping from the envelope (PRD §Envelope Schema) to the Parquet schema:

| Parquet column | Type | Source |
|---|---|---|
| `envelope_id` | string | `envelope_id` |
| `correlation_id` | string (nullable) | `correlation_id` |
| `schema_version` | string | `schema_version` |
| `source_system` | string | `source.system` |
| `source_event_hub` | string | `source.event_hub` |
| `source_original_timestamp` | string (nullable) | `source.original_timestamp` |
| `event_type` | string | `event.type` |
| `event_received_at` | string | `event.received_at` |
| `event_processed_at` | string | `event.processed_at` |
| `pipeline_id` | string | `pipeline.pipeline_id` |
| `retry_count` | int64 | `pipeline.retry_count` |
| `processing_ms` | int64 | `pipeline.processing_ms` |
| `metadata_json` | string | `json.dumps(metadata)` |
| `payload_json` | string | `json.dumps(payload)` |

Timestamps stay as ISO8601 strings to match the envelope shape and avoid per-write timezone/parse logic — downstream casts at query time if needed. The schema is declared once as a module-level `pa.schema(...)` so every batch from a single worker writes a stable Parquet schema.

## Consequences

- Common queries (filter by source, correlation_id, event type, retry_count; project a few columns) get column pruning and predicate pushdown.
- Per-source metadata changes do not break writes — the JSON string column absorbs any shape.
- Downstream queries on metadata fields require `from_json(metadata_json, ...)` (or equivalent) at read time; acceptable for the metadata path because each per-source consumer already knows its metadata shape.
- Two values are JSON-serialised on the write hot path (`metadata`, `payload`); negligible cost relative to Parquet encoding and the network upload.
- If a future need genuinely calls for typed metadata columns for one source (e.g., a heavy analytics consumer), the per-source path partition makes it straightforward to introduce a source-specific table layout without disturbing other sources.
- Bumping `schema_version` will at most add or remove top-level columns — Fabric handles per-file schema evolution for nullable additions; breaking removals would require a deliberate migration regardless of column layout.
