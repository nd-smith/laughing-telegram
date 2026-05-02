# 0006 — Prometheus metrics

## Goal

Define every metric instrument listed in PRD §Observability §Metrics and provide a function that starts the Prometheus HTTP scrape endpoint. Wiring into actual processing happens in later issues.

## Scope

- `pipeline/metrics.py` declaring the eight instruments from the PRD with `source` as a label (and `status` on `events_processed_total`):
  - `events_received_total` — Counter
  - `events_processed_total` — Counter (labels: `source`, `status`)
  - `events_dlq_total` — Counter
  - `processing_duration_seconds` — Histogram
  - `batch_write_duration_seconds` — Histogram
  - `batch_size` — Histogram
  - `kafka_publish_duration_seconds` — Histogram
  - `buffer_size` — Gauge
- `start_metrics_server(port: int)` that calls `prometheus_client.start_http_server`.
- `tests/test_metrics.py` covering:
  - All eight instruments present with the expected names and labels.
  - HTTP endpoint, when started on a free port, returns a `200` with text in Prometheus exposition format.

## Out of scope

- Wiring metrics into consumer / writer / publisher / processor (issues 0007–0010 own their own metric updates).
- Custom collectors or pushgateway integration.

## Acceptance criteria

- All instruments importable from `pipeline.metrics`.
- `tests/test_metrics.py` passes.

## Notes

- Use `prometheus_client` directly. Don't wrap it — wrappers add nothing here.
- **Ask** if histogram bucket boundaries should differ from `prometheus_client` defaults; defaults are fine for a first cut.
