"""Tests for pipeline.envelope."""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from pipeline.envelope import SCHEMA_VERSION, build_envelope


def _valid_inputs(**overrides):
    base = {
        "raw_event": {"type": "status_update", "data": {"policy": {"id": "P-1"}, "status": "open"}},
        "metadata": {"policy_id": "P-1", "status": "open"},
        "event_type": "status_update",
        "correlation_id": "corr-123",
        "source_system": "source-a",
        "source_event_hub": "source-a-events",
        "source_original_timestamp": "2026-05-01T12:00:00+00:00",
        "pipeline_id": "worker-1",
        "retry_count": 0,
        "received_at": datetime.now(timezone.utc) - timedelta(milliseconds=5),
    }
    base.update(overrides)
    return base


def test_all_required_fields_populated():
    env = build_envelope(**_valid_inputs())

    assert set(env.keys()) == {
        "envelope_id",
        "correlation_id",
        "schema_version",
        "source",
        "event",
        "metadata",
        "pipeline",
        "payload",
    }
    assert set(env["source"].keys()) == {"system", "event_hub", "original_timestamp"}
    assert set(env["event"].keys()) == {"type", "received_at", "processed_at"}
    assert set(env["pipeline"].keys()) == {"pipeline_id", "retry_count", "processing_ms"}

    assert env["source"]["system"] == "source-a"
    assert env["source"]["event_hub"] == "source-a-events"
    assert env["source"]["original_timestamp"] == "2026-05-01T12:00:00+00:00"
    assert env["event"]["type"] == "status_update"
    assert env["metadata"] == {"policy_id": "P-1", "status": "open"}
    assert env["pipeline"]["pipeline_id"] == "worker-1"
    assert env["pipeline"]["retry_count"] == 0


def test_envelope_id_is_uuid_v4():
    env = build_envelope(**_valid_inputs())
    parsed = uuid.UUID(env["envelope_id"])
    assert parsed.version == 4
    assert parsed.variant == uuid.RFC_4122


def test_envelope_ids_are_unique_per_call():
    a = build_envelope(**_valid_inputs())
    b = build_envelope(**_valid_inputs())
    assert a["envelope_id"] != b["envelope_id"]


def test_correlation_id_set_when_provided():
    env = build_envelope(**_valid_inputs(correlation_id="abc-xyz"))
    assert env["correlation_id"] == "abc-xyz"


def test_correlation_id_null_when_absent():
    env = build_envelope(**_valid_inputs(correlation_id=None))
    assert env["correlation_id"] is None


def test_source_original_timestamp_null_when_absent():
    env = build_envelope(**_valid_inputs(source_original_timestamp=None))
    assert env["source"]["original_timestamp"] is None


def test_received_at_le_processed_at_and_processing_ms_nonneg():
    received = datetime.now(timezone.utc) - timedelta(milliseconds=10)
    env = build_envelope(**_valid_inputs(received_at=received))

    received_parsed = datetime.fromisoformat(env["event"]["received_at"])
    processed_parsed = datetime.fromisoformat(env["event"]["processed_at"])

    assert received_parsed <= processed_parsed
    assert env["pipeline"]["processing_ms"] >= 0


def test_payload_byte_equivalent_to_input():
    raw = {"type": "document_ready", "data": {"url": "https://example.com/x", "n": 7}}
    env = build_envelope(**_valid_inputs(raw_event=raw))
    assert json.dumps(env["payload"], sort_keys=True) == json.dumps(raw, sort_keys=True)


def test_schema_version_matches_constant():
    env = build_envelope(**_valid_inputs())
    assert env["schema_version"] == SCHEMA_VERSION
    assert SCHEMA_VERSION == "1.0"


def test_retry_count_passthrough():
    env = build_envelope(**_valid_inputs(retry_count=2))
    assert env["pipeline"]["retry_count"] == 2


def test_keyword_only_signature():
    with pytest.raises(TypeError):
        build_envelope({}, {}, "t", None, "s", "h", None, "p", 0, datetime.now(timezone.utc))  # type: ignore[misc]
