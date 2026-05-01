# Issue Index

- [0001 — Project scaffolding & dependencies](0001_project_scaffolding_and_dependencies.md) {2026-05-01} — repo directories, `__init__.py` files, `requirements.txt`
- [0002 — Envelope construction](0002_envelope_construction.md) {2026-05-01} — `pipeline/envelope.py` pure builder + tests
- [0003 — Event validation](0003_event_validation.md) {2026-05-01} — `pipeline/validation.py` minimal required-fields check + tests
- [0004 — Source module contract & loader](0004_source_module_contract_and_loader.md) {2026-05-01} — `pipeline/sources/__init__.py` loader, contract docstring, fixture-based tests
- [0005 — Structured JSON logging](0005_structured_json_logging.md) {2026-05-01} — `shared/logging.py` JSON logger with source/correlation_id/envelope_id context
- [0006 — Prometheus metrics](0006_prometheus_metrics.md) {2026-05-01} — `pipeline/metrics.py` instruments + HTTP server start
- [0007 — Event Hub consumer](0007_event_hub_consumer.md) {2026-05-01} — sync `azure-eventhub` consumer with checkpointing and DefaultAzureCredential
- [0008 — OneLake Parquet writer](0008_onelake_parquet_writer.md) {2026-05-01} — buffered Parquet flush to ADLS Gen2 on interval/size
- [0009 — Kafka publisher](0009_kafka_publisher.md) {2026-05-01} — `confluent-kafka` producer with delivery confirmation
- [0010 — Processing pipeline & retry/DLQ orchestration](0010_processing_pipeline_and_retry_dlq.md) {2026-05-01} — per-event glue, 3-retry exponential backoff, DLQ topic publish
- [0011 — Worker entry point & main loop](0011_worker_entry_point_and_main_loop.md) {2026-05-01} — `pipeline/__main__.py` CLI, wiring, SIGTERM/SIGINT graceful shutdown
