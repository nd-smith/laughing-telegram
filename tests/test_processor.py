"""Tests for pipeline.processor.

Real ``validate`` and ``build_envelope``; the writer, publisher, and
extractor are mocked. ``time.sleep`` is injected so backoff tests run
instantaneously.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from unittest.mock import MagicMock, patch

import pytest

from pipeline import metrics
from pipeline import processor as processor_module
from pipeline.processor import Processor
from pipeline.publisher import PublishError


def _raw_event() -> dict[str, Any]:
    return {
        "correlation_id": "c-1",
        "timestamp": "2026-05-02T11:59:00+00:00",
        "type": "status_update",
        "data": {"policy": {"id": "P-100"}, "status": "active"},
    }


def _received_at() -> datetime:
    return datetime(2026, 5, 2, 12, 0, 0, tzinfo=timezone.utc)


def _default_extractor(event: dict[str, Any]) -> tuple[dict[str, Any], str]:
    return (
        {
            "policy_id": event["data"]["policy"]["id"],
            "status": event["data"]["status"],
        },
        event["type"],
    )


def _make_processor(
    *,
    source_name: str = "source-a",
    max_retries: int = 3,
    backoff_base_s: float = 0.0,
    extractor: Callable[..., Any] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> tuple[Processor, MagicMock, MagicMock, list[float]]:
    writer = MagicMock(name="writer")
    publisher = MagicMock(name="publisher")
    sleeps: list[float] = []
    if sleep is None:
        def sleep(d: float) -> None:
            sleeps.append(d)
    p = Processor(
        source_name=source_name,
        source_event_hub=f"{source_name}-events",
        pipeline_id="worker-0",
        extractor=extractor if extractor is not None else _default_extractor,
        required_fields=("data",),
        writer=writer,
        publisher=publisher,
        kafka_output_topic=f"propgateway.{source_name}",
        max_retries=max_retries,
        backoff_base_s=backoff_base_s,
        sleep=sleep,
    )
    return p, writer, publisher, sleeps


def _counter_value(counter: Any, **labels: str) -> float:
    for family in counter.collect():
        for sample in family.samples:
            if sample.name == family.name + "_total" and all(
                sample.labels.get(k) == v for k, v in labels.items()
            ):
                return sample.value
    return 0.0


def _hist_count(hist: Any, **labels: str) -> float:
    for family in hist.collect():
        for sample in family.samples:
            if sample.name == family.name + "_count" and all(
                sample.labels.get(k) == v for k, v in labels.items()
            ):
                return sample.value
    return 0.0


# --- Happy path ---


def test_happy_path_calls_each_step_once():
    p, writer, publisher, sleeps = _make_processor()
    p.process(_raw_event(), _received_at())

    assert writer.add.call_count == 1
    assert publisher.publish.call_count == 1
    assert sleeps == []


def test_happy_path_publishes_envelope_to_source_topic():
    p, _, publisher, _ = _make_processor(source_name="source-a")
    p.process(_raw_event(), _received_at())

    topic, envelope = publisher.publish.call_args.args
    assert topic == "propgateway.source-a"
    assert envelope["source"]["system"] == "source-a"
    assert envelope["source"]["event_hub"] == "source-a-events"
    assert envelope["source"]["original_timestamp"] == "2026-05-02T11:59:00+00:00"
    assert envelope["event"]["type"] == "status_update"
    assert envelope["correlation_id"] == "c-1"
    assert envelope["metadata"] == {"policy_id": "P-100", "status": "active"}
    assert envelope["payload"] == _raw_event()
    assert envelope["pipeline"]["pipeline_id"] == "worker-0"
    assert envelope["pipeline"]["retry_count"] == 0


def test_writer_and_publisher_get_same_envelope_on_one_attempt():
    p, writer, publisher, _ = _make_processor()
    p.process(_raw_event(), _received_at())

    writer_env = writer.add.call_args.args[0]
    pub_env = publisher.publish.call_args.args[1]
    assert writer_env is pub_env


def test_correlation_id_and_original_timestamp_default_to_null_when_absent():
    p, _, publisher, _ = _make_processor()
    raw = {"data": {"policy": {"id": "P-1"}, "status": "ok"}, "type": "status_update"}
    p.process(raw, _received_at())

    envelope = publisher.publish.call_args.args[1]
    assert envelope["correlation_id"] is None
    assert envelope["source"]["original_timestamp"] is None


# --- Failure modes (each goes to DLQ after retries) ---


def test_validation_failure_goes_to_dlq_after_retries():
    p, writer, publisher, sleeps = _make_processor()
    raw = {"missing_data_field": True}
    p.process(raw, _received_at())

    writer.add.assert_not_called()
    assert publisher.publish.call_count == 1
    topic, payload = publisher.publish.call_args.args
    assert topic == "propgateway.source-a.dlq"
    assert payload["raw_event"] == raw
    assert "missing required field" in payload["error"]
    assert payload["retry_count"] == 3
    assert len(sleeps) == 3


def test_extract_failure_goes_to_dlq_after_retries():
    def bad_extract(_: Any) -> tuple[dict, str]:
        raise ValueError("bad shape")

    p, writer, publisher, sleeps = _make_processor(extractor=bad_extract)
    p.process(_raw_event(), _received_at())

    writer.add.assert_not_called()
    assert publisher.publish.call_count == 1
    topic, payload = publisher.publish.call_args.args
    assert topic == "propgateway.source-a.dlq"
    assert payload["error"] == "bad shape"
    assert payload["retry_count"] == 3
    assert len(sleeps) == 3


def test_envelope_failure_goes_to_dlq_after_retries():
    p, writer, publisher, sleeps = _make_processor()
    with patch.object(
        processor_module,
        "build_envelope",
        side_effect=RuntimeError("envelope boom"),
    ):
        p.process(_raw_event(), _received_at())

    writer.add.assert_not_called()
    assert publisher.publish.call_count == 1
    topic, payload = publisher.publish.call_args.args
    assert topic == "propgateway.source-a.dlq"
    assert payload["error"] == "envelope boom"
    assert len(sleeps) == 3


def test_writer_failure_goes_to_dlq_after_retries():
    p, writer, publisher, sleeps = _make_processor()
    writer.add.side_effect = RuntimeError("write boom")
    p.process(_raw_event(), _received_at())

    assert writer.add.call_count == 4  # 1 initial + 3 retries
    assert publisher.publish.call_count == 1  # DLQ only
    topic, payload = publisher.publish.call_args.args
    assert topic == "propgateway.source-a.dlq"
    assert payload["error"] == "write boom"
    assert len(sleeps) == 3


def test_publisher_failure_goes_to_dlq_after_retries():
    p, writer, publisher, sleeps = _make_processor()
    publisher.publish.side_effect = [
        PublishError("kafka boom"),
        PublishError("kafka boom"),
        PublishError("kafka boom"),
        PublishError("kafka boom"),
        None,
    ]
    p.process(_raw_event(), _received_at())

    assert writer.add.call_count == 4
    assert publisher.publish.call_count == 5
    topic, payload = publisher.publish.call_args.args
    assert topic == "propgateway.source-a.dlq"
    assert payload["error"] == "kafka boom"
    assert len(sleeps) == 3


# --- Recovery ---


def test_one_transient_failure_then_success_no_dlq():
    p, writer, publisher, sleeps = _make_processor()
    publisher.publish.side_effect = [PublishError("transient"), None]
    p.process(_raw_event(), _received_at())

    assert writer.add.call_count == 2
    assert publisher.publish.call_count == 2
    final_topic = publisher.publish.call_args.args[0]
    assert final_topic == "propgateway.source-a"
    assert len(sleeps) == 1


def test_retry_count_increments_in_envelope_per_attempt():
    p, writer, publisher, _ = _make_processor()
    publisher.publish.side_effect = [
        PublishError("transient"),
        PublishError("transient"),
        None,
    ]
    p.process(_raw_event(), _received_at())

    retry_counts = [
        call.args[0]["pipeline"]["retry_count"]
        for call in writer.add.call_args_list
    ]
    assert retry_counts == [0, 1, 2]


# --- Backoff ---


def test_backoff_doubles_each_retry():
    captured: list[float] = []
    p, _, publisher, _ = _make_processor(
        backoff_base_s=0.5,
        sleep=captured.append,
    )
    # 4 source-topic publish failures, then DLQ publish succeeds.
    publisher.publish.side_effect = [PublishError("boom")] * 4 + [None]
    p.process(_raw_event(), _received_at())

    # 3 retries → sleeps: 0.5*2^0, 0.5*2^1, 0.5*2^2
    assert captured == [0.5, 1.0, 2.0]


def test_no_sleep_after_final_failed_attempt():
    captured: list[float] = []
    p, _, publisher, _ = _make_processor(
        backoff_base_s=1.0,
        sleep=captured.append,
    )
    publisher.publish.side_effect = [PublishError("boom")] * 4 + [None]
    p.process(_raw_event(), _received_at())

    # 4 attempts → 3 sleeps between, none after the final one.
    assert len(captured) == 3


def test_max_retries_configurable():
    captured: list[float] = []
    p, writer, publisher, _ = _make_processor(
        max_retries=1,
        backoff_base_s=0.1,
        sleep=captured.append,
    )
    # 2 source-topic publish failures, then DLQ publish succeeds.
    publisher.publish.side_effect = [PublishError("boom")] * 2 + [None]
    p.process(_raw_event(), _received_at())

    assert writer.add.call_count == 2  # 1 initial + 1 retry
    assert len(captured) == 1
    # 2 failed source-topic publishes + 1 DLQ publish.
    assert publisher.publish.call_count == 3


def test_max_retries_zero_skips_retry_goes_straight_to_dlq():
    captured: list[float] = []
    p, _, publisher, _ = _make_processor(
        max_retries=0,
        backoff_base_s=1.0,
        sleep=captured.append,
    )
    p.process({"missing": "data"}, _received_at())

    assert captured == []  # no sleeps
    topic, payload = publisher.publish.call_args.args
    assert topic == "propgateway.source-a.dlq"
    assert payload["retry_count"] == 0


# --- DLQ payload shape (PRD §Dead Letter Queue, ADR 0018) ---


def test_dlq_payload_has_exactly_the_prd_fields():
    p, _, publisher, _ = _make_processor()
    raw = {"missing": "data"}
    p.process(raw, _received_at())

    payload = publisher.publish.call_args.args[1]
    assert set(payload.keys()) == {
        "raw_event",
        "error",
        "stack_trace",
        "retry_count",
        "failed_at",
    }
    assert payload["raw_event"] == raw
    assert isinstance(payload["error"], str)
    assert isinstance(payload["stack_trace"], str)
    assert payload["retry_count"] == 3
    # Round-trips as ISO8601.
    datetime.fromisoformat(payload["failed_at"])


def test_dlq_payload_stack_trace_is_real_traceback():
    def bad_extract(_: Any) -> tuple[dict, str]:
        raise RuntimeError("specific marker")

    p, _, publisher, _ = _make_processor(extractor=bad_extract)
    p.process(_raw_event(), _received_at())

    payload = publisher.publish.call_args.args[1]
    assert "RuntimeError: specific marker" in payload["stack_trace"]
    assert "bad_extract" in payload["stack_trace"]


def test_dlq_payload_is_flat_dict_not_envelope():
    """Per ADR 0018: DLQ payload is the literal four PRD fields, not an envelope."""
    p, _, publisher, _ = _make_processor()
    p.process({"missing": "data"}, _received_at())

    payload = publisher.publish.call_args.args[1]
    assert "envelope_id" not in payload
    assert "schema_version" not in payload
    assert "metadata" not in payload
    assert "source" not in payload


# --- DLQ topic naming (PRD §Dead Letter Queue) ---


@pytest.mark.parametrize("source_name", ["source-a", "source-b", "weird-name"])
def test_dlq_topic_name_format(source_name: str) -> None:
    p, _, publisher, _ = _make_processor(source_name=source_name)
    p.process({"missing": "data"}, _received_at())

    topic = publisher.publish.call_args.args[0]
    assert topic == f"propgateway.{source_name}.dlq"


# --- Metrics ---


def test_success_metric_incremented():
    p, _, _, _ = _make_processor(source_name="metrics-success")
    before = _counter_value(
        metrics.events_processed_total, source="metrics-success", status="success"
    )
    p.process(_raw_event(), _received_at())
    after = _counter_value(
        metrics.events_processed_total, source="metrics-success", status="success"
    )
    assert after == before + 1


def test_failure_metric_incremented_on_dlq():
    p, _, _, _ = _make_processor(source_name="metrics-failure")
    before = _counter_value(
        metrics.events_processed_total, source="metrics-failure", status="failure"
    )
    p.process({"missing": "data"}, _received_at())
    after = _counter_value(
        metrics.events_processed_total, source="metrics-failure", status="failure"
    )
    assert after == before + 1


def test_dlq_metric_incremented():
    p, _, _, _ = _make_processor(source_name="metrics-dlq")
    before = _counter_value(metrics.events_dlq_total, source="metrics-dlq")
    p.process({"missing": "data"}, _received_at())
    after = _counter_value(metrics.events_dlq_total, source="metrics-dlq")
    assert after == before + 1


def test_processing_duration_recorded_on_success():
    p, _, _, _ = _make_processor(source_name="metrics-duration-success")
    before = _hist_count(
        metrics.processing_duration_seconds, source="metrics-duration-success"
    )
    p.process(_raw_event(), _received_at())
    after = _hist_count(
        metrics.processing_duration_seconds, source="metrics-duration-success"
    )
    assert after == before + 1


def test_processing_duration_recorded_on_failure():
    p, _, _, _ = _make_processor(source_name="metrics-duration-failure")
    before = _hist_count(
        metrics.processing_duration_seconds, source="metrics-duration-failure"
    )
    p.process({"missing": "data"}, _received_at())
    after = _hist_count(
        metrics.processing_duration_seconds, source="metrics-duration-failure"
    )
    assert after == before + 1


# --- DLQ publish failure ---


def test_dlq_publish_failure_propagates():
    p, _, publisher, _ = _make_processor()
    publisher.publish.side_effect = PublishError("kafka totally down")
    with pytest.raises(PublishError):
        p.process({"missing": "data"}, _received_at())


def test_failure_metric_still_incremented_when_dlq_publish_fails():
    p, _, publisher, _ = _make_processor(source_name="dlq-fail-metric")
    publisher.publish.side_effect = PublishError("kafka totally down")
    before = _counter_value(
        metrics.events_processed_total, source="dlq-fail-metric", status="failure"
    )
    with pytest.raises(PublishError):
        p.process({"missing": "data"}, _received_at())
    after = _counter_value(
        metrics.events_processed_total, source="dlq-fail-metric", status="failure"
    )
    assert after == before + 1


def test_dlq_metric_not_incremented_when_dlq_publish_fails():
    p, _, publisher, _ = _make_processor(source_name="dlq-fail-no-metric")
    publisher.publish.side_effect = PublishError("kafka totally down")
    before = _counter_value(metrics.events_dlq_total, source="dlq-fail-no-metric")
    with pytest.raises(PublishError):
        p.process({"missing": "data"}, _received_at())
    after = _counter_value(metrics.events_dlq_total, source="dlq-fail-no-metric")
    assert after == before
