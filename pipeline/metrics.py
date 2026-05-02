"""Prometheus instruments per PRD §Observability §Metrics.

Instrument declarations only. Wiring into consumer/writer/publisher/processor
is owned by those modules. `prometheus_client` is used directly; no wrapper.

Histograms use `prometheus_client`'s default bucket boundaries.
"""

from prometheus_client import Counter, Gauge, Histogram, start_http_server

events_received_total = Counter(
    "events_received_total",
    "Events received from Event Hub.",
    ["source"],
)

events_processed_total = Counter(
    "events_processed_total",
    "Events fully processed by the pipeline.",
    ["source", "status"],
)

events_dlq_total = Counter(
    "events_dlq_total",
    "Events sent to the dead-letter queue.",
    ["source"],
)

processing_duration_seconds = Histogram(
    "processing_duration_seconds",
    "Wall-clock time to process a single event end-to-end.",
    ["source"],
)

batch_write_duration_seconds = Histogram(
    "batch_write_duration_seconds",
    "Wall-clock time to flush one Parquet batch to OneLake.",
    ["source"],
)

batch_size = Histogram(
    "batch_size",
    "Number of events in a flushed Parquet batch.",
    ["source"],
)

kafka_publish_duration_seconds = Histogram(
    "kafka_publish_duration_seconds",
    "Wall-clock time to publish one envelope to Kafka.",
    ["source"],
)

buffer_size = Gauge(
    "buffer_size",
    "Current number of events in the writer buffer.",
    ["source"],
)


def start_metrics_server(port: int) -> None:
    """Start the Prometheus HTTP scrape endpoint on `port` (binds 0.0.0.0)."""
    start_http_server(port)
