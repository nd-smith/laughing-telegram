"""Tests for pipeline.metrics."""

import socket
import urllib.request

import pytest
from prometheus_client import Counter, Gauge, Histogram

from pipeline import metrics


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_all_eight_instruments_exported_with_expected_types():
    assert isinstance(metrics.events_received_total, Counter)
    assert isinstance(metrics.events_processed_total, Counter)
    assert isinstance(metrics.events_dlq_total, Counter)
    assert isinstance(metrics.processing_duration_seconds, Histogram)
    assert isinstance(metrics.batch_write_duration_seconds, Histogram)
    assert isinstance(metrics.batch_size, Histogram)
    assert isinstance(metrics.kafka_publish_duration_seconds, Histogram)
    assert isinstance(metrics.buffer_size, Gauge)


def test_source_labelled_counters_accept_source_label():
    metrics.events_received_total.labels(source="source-a").inc()
    metrics.events_dlq_total.labels(source="source-a").inc()


def test_events_processed_total_requires_source_and_status_labels():
    metrics.events_processed_total.labels(source="source-a", status="success").inc()
    metrics.events_processed_total.labels(source="source-a", status="failure").inc()
    with pytest.raises(ValueError):
        metrics.events_processed_total.labels(source="source-a")


def test_histograms_accept_source_label_and_observe():
    metrics.processing_duration_seconds.labels(source="source-a").observe(0.01)
    metrics.batch_write_duration_seconds.labels(source="source-a").observe(0.1)
    metrics.batch_size.labels(source="source-a").observe(500)
    metrics.kafka_publish_duration_seconds.labels(source="source-a").observe(0.05)


def test_buffer_size_gauge_accepts_source_label_and_set():
    metrics.buffer_size.labels(source="source-a").set(42)


def test_http_endpoint_returns_200_with_prometheus_exposition():
    port = _free_port()
    metrics.start_metrics_server(port)

    with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics") as resp:
        assert resp.status == 200
        body = resp.read().decode()

    assert "# HELP" in body
    assert "# TYPE" in body
    for name in (
        "events_received_total",
        "events_processed_total",
        "events_dlq_total",
        "processing_duration_seconds",
        "batch_write_duration_seconds",
        "batch_size",
        "kafka_publish_duration_seconds",
        "buffer_size",
    ):
        assert name in body
