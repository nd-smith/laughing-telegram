"""Tests for pipeline.publisher.

The ``confluent_kafka.Producer`` is mocked at the module boundary so no
network I/O is attempted. The mock is configured to drive the
``on_delivery`` callback synchronously from ``flush()`` — which matches
how ``confluent_kafka`` actually behaves: callbacks fire from inside
``flush()`` (or ``poll()``) on the calling thread.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pipeline import metrics
from pipeline import publisher as publisher_module


def _make_publisher(
    *,
    source_name: str = "source-a",
    flush_timeout_s: float = 5.0,
) -> tuple[publisher_module.KafkaPublisher, MagicMock]:
    """Build a KafkaPublisher with a fully-mocked ``Producer``."""
    prod = MagicMock(name="producer")
    p = publisher_module.KafkaPublisher(
        producer_config={"bootstrap.servers": "broker:9092"},
        source_name=source_name,
        flush_timeout_s=flush_timeout_s,
        producer=prod,
    )
    return p, prod


def _arm_flush_to_invoke_callback(
    prod: MagicMock,
    *,
    err: Any = None,
    partition: int = 0,
    offset: int = 1,
) -> None:
    """Configure ``prod.flush`` to fire the latest ``on_delivery`` synchronously.

    Mirrors ``confluent_kafka.Producer`` behaviour: ``flush()`` runs the
    delivery-report callbacks of every message produced since the last
    drain on the calling thread, then returns 0 when the queue is empty.
    """

    def fake_flush(timeout: float) -> int:
        on_delivery = prod.produce.call_args.kwargs["on_delivery"]
        msg = MagicMock(name="msg")
        msg.partition.return_value = partition
        msg.offset.return_value = offset
        on_delivery(err, msg)
        return 0

    prod.flush.side_effect = fake_flush


def _envelope() -> dict:
    return {
        "envelope_id": "e-1",
        "correlation_id": "c-1",
        "schema_version": "1.0",
        "source": {
            "system": "source-a",
            "event_hub": "source-a-events",
            "original_timestamp": "2026-05-02T12:00:00+00:00",
        },
        "event": {
            "type": "status_update",
            "received_at": "2026-05-02T12:00:01+00:00",
            "processed_at": "2026-05-02T12:00:01.050000+00:00",
        },
        "metadata": {"policy_id": "P-123", "status": "active"},
        "pipeline": {
            "pipeline_id": "worker-0",
            "retry_count": 0,
            "processing_ms": 50,
        },
        "payload": {"raw": "anything", "nested": {"a": 1, "b": [1, 2, 3]}},
    }


def test_constructor_creates_producer_when_none_provided():
    with patch.object(publisher_module, "Producer") as ProducerCls:
        ProducerCls.return_value = MagicMock(name="producer")
        p = publisher_module.KafkaPublisher(
            producer_config={"bootstrap.servers": "broker:9092"},
            source_name="source-a",
        )
    ProducerCls.assert_called_once_with({"bootstrap.servers": "broker:9092"})
    assert p._producer is ProducerCls.return_value


def test_constructor_accepts_injected_producer():
    prod = MagicMock(name="producer")
    p = publisher_module.KafkaPublisher(
        producer_config={"bootstrap.servers": "broker:9092"},
        source_name="source-a",
        producer=prod,
    )
    assert p._producer is prod
    prod.assert_not_called()


def test_publish_calls_produce_with_topic_value_and_callback():
    pub, prod = _make_publisher()
    _arm_flush_to_invoke_callback(prod)

    pub.publish("propgateway.source-a", _envelope())

    prod.produce.assert_called_once()
    args, kwargs = prod.produce.call_args
    assert args == ("propgateway.source-a",)
    assert isinstance(kwargs["value"], bytes)
    assert callable(kwargs["on_delivery"])


def test_publish_serialises_envelope_to_utf8_json_bytes():
    pub, prod = _make_publisher()
    _arm_flush_to_invoke_callback(prod)
    env = _envelope()

    pub.publish("topic", env)

    payload = prod.produce.call_args.kwargs["value"]
    assert isinstance(payload, bytes)
    decoded = json.loads(payload.decode("utf-8"))
    assert decoded == env


def test_publish_handles_nested_dicts_lists_and_nullable_fields():
    pub, prod = _make_publisher()
    _arm_flush_to_invoke_callback(prod)
    env = _envelope()
    env["correlation_id"] = None
    env["source"]["original_timestamp"] = None
    env["payload"] = {"deep": {"deeper": [{"a": 1}, {"b": None}]}}

    pub.publish("topic", env)

    payload = prod.produce.call_args.kwargs["value"]
    decoded = json.loads(payload.decode("utf-8"))
    assert decoded["correlation_id"] is None
    assert decoded["source"]["original_timestamp"] is None
    assert decoded["payload"] == {"deep": {"deeper": [{"a": 1}, {"b": None}]}}


def test_publish_serialises_pre_stringified_uuid_and_iso_timestamp():
    """ADR 0016: callers (envelope.py) own type conversion. Stringified
    UUIDs and ISO8601 timestamps must serialise correctly."""
    pub, prod = _make_publisher()
    _arm_flush_to_invoke_callback(prod)
    env = _envelope()
    env["envelope_id"] = str(uuid.UUID("12345678-1234-5678-1234-567812345678"))
    env["event"]["received_at"] = datetime(
        2026, 5, 2, 12, 0, 1, tzinfo=timezone.utc
    ).isoformat()

    pub.publish("topic", env)

    payload = prod.produce.call_args.kwargs["value"]
    decoded = json.loads(payload.decode("utf-8"))
    assert decoded["envelope_id"] == "12345678-1234-5678-1234-567812345678"
    assert decoded["event"]["received_at"] == "2026-05-02T12:00:01+00:00"


def test_publish_raises_typeerror_for_non_json_native_values():
    """ADR 0016: strict serialisation surfaces upstream bugs as TypeError."""
    pub, prod = _make_publisher()
    env = _envelope()
    env["envelope_id"] = uuid.UUID("12345678-1234-5678-1234-567812345678")

    with pytest.raises(TypeError):
        pub.publish("topic", env)

    prod.produce.assert_not_called()
    prod.flush.assert_not_called()


def test_successful_delivery_does_not_raise():
    pub, prod = _make_publisher()
    _arm_flush_to_invoke_callback(prod)

    pub.publish("topic", _envelope())  # must not raise


def test_failed_delivery_raises_publish_error():
    pub, prod = _make_publisher()
    _arm_flush_to_invoke_callback(prod, err="broker rejected message")

    with pytest.raises(publisher_module.PublishError, match="broker rejected message"):
        pub.publish("topic", _envelope())


def test_flush_timeout_raises_publish_error():
    """If flush() returns >0, the message did not deliver in time."""
    pub, prod = _make_publisher(flush_timeout_s=2.0)
    prod.flush.return_value = 1  # one message still queued after timeout

    with pytest.raises(publisher_module.PublishError, match="2.0s"):
        pub.publish("topic", _envelope())


def test_flush_returns_zero_but_callback_never_fired_raises_publish_error():
    """Defensive: if flush() returns 0 but the callback never fired,
    treat as timeout — the publisher cannot confirm delivery."""
    pub, prod = _make_publisher()
    prod.flush.return_value = 0  # no callback invoked

    with pytest.raises(publisher_module.PublishError, match="did not complete"):
        pub.publish("topic", _envelope())


def _publish_duration_count(source: str) -> float:
    """Pull the histogram's ``_count`` sample for the given source label."""
    for family in metrics.kafka_publish_duration_seconds.collect():
        for sample in family.samples:
            if (
                sample.name == "kafka_publish_duration_seconds_count"
                and sample.labels.get("source") == source
            ):
                return sample.value
    return 0.0


def test_publish_records_duration_metric_on_success():
    pub, prod = _make_publisher(source_name="source-metric-success")
    _arm_flush_to_invoke_callback(prod)
    before = _publish_duration_count("source-metric-success")

    pub.publish("topic", _envelope())

    assert _publish_duration_count("source-metric-success") == before + 1


def test_publish_records_duration_metric_on_failure():
    pub, prod = _make_publisher(source_name="source-metric-failure")
    _arm_flush_to_invoke_callback(prod, err="kaboom")
    before = _publish_duration_count("source-metric-failure")

    with pytest.raises(publisher_module.PublishError):
        pub.publish("topic", _envelope())

    assert _publish_duration_count("source-metric-failure") == before + 1


def test_flush_method_delegates_to_producer():
    pub, prod = _make_publisher()
    prod.flush.return_value = 0

    pub.flush(7.5)

    prod.flush.assert_called_once_with(7.5)


def test_flush_method_logs_warning_when_messages_remain(caplog):
    pub, prod = _make_publisher()
    prod.flush.return_value = 3

    with caplog.at_level("WARNING", logger="pipeline.publisher"):
        pub.flush(1.0)

    assert any(
        "kafka publisher flush left messages in queue" in r.message
        for r in caplog.records
    )
