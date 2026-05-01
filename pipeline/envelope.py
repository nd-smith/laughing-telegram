"""Envelope construction per PRD §Envelope Schema.

Pure module: no I/O, no global state, stdlib only.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0"


def build_envelope(
    *,
    raw_event: dict[str, Any],
    metadata: dict[str, Any],
    event_type: str,
    correlation_id: str | None,
    source_system: str,
    source_event_hub: str,
    source_original_timestamp: str | None,
    pipeline_id: str,
    retry_count: int,
    received_at: datetime,
) -> dict[str, Any]:
    """Wrap a raw event in the standard envelope.

    `envelope_id`, `processed_at`, and `processing_ms` are generated here;
    every other field comes from the caller.

    `received_at` must be timezone-aware so the elapsed-time subtraction
    against the tz-aware `processed_at` is well-defined.
    """
    processed_at = datetime.now(timezone.utc)
    processing_ms = int((processed_at - received_at).total_seconds() * 1000)

    return {
        "envelope_id": str(uuid.uuid4()),
        "correlation_id": correlation_id,
        "schema_version": SCHEMA_VERSION,
        "source": {
            "system": source_system,
            "event_hub": source_event_hub,
            "original_timestamp": source_original_timestamp,
        },
        "event": {
            "type": event_type,
            "received_at": received_at.isoformat(),
            "processed_at": processed_at.isoformat(),
        },
        "metadata": metadata,
        "pipeline": {
            "pipeline_id": pipeline_id,
            "retry_count": retry_count,
            "processing_ms": processing_ms,
        },
        "payload": raw_event,
    }
