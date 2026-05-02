"""Per-event processing pipeline with retry/DLQ orchestration.

Glues the pure components (``validate``, the source extractor,
``build_envelope``) and the I/O components (``OneLakeWriter``,
``KafkaPublisher``) into a single per-event flow with the
retry-3x-then-DLQ semantics from PRD §Error Handling.

Class shape (ADR 0017): mirrors the wiring style of ``KafkaPublisher`` /
``OneLakeWriter`` / ``EventHubConsumer`` — per-source state captured in
``__init__``, one ``process(raw_event, received_at)`` method per event.

Retry policy (ADR 0019): up to ``max_retries`` retries (default 3) after
the first attempt fails. Sleeps ``backoff_base_s * 2**attempt`` between
attempts — default 1s, 2s, 4s. ``sleep`` is injected so tests run fast.
The whole 5-step flow re-runs on retry — the writer may receive multiple
envelopes for a single source event with different ``retry_count`` values.

DLQ payload (ADR 0018): the literal four PRD §Dead Letter Queue fields
in a flat dict, not an envelope. The DLQ publish path runs even when
validate / extract / envelope-build is the failing step, so it must not
depend on any of those having succeeded.

If the DLQ publish itself fails, ``process()`` re-raises so the consumer
wrapper (ADR 0011) skips checkpointing — the event will be re-delivered
on the next session, which is the right behaviour for "Kafka is down".
The failure metric increments either way.
"""

from __future__ import annotations

import logging
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from pipeline import metrics
from pipeline.envelope import build_envelope
from pipeline.publisher import KafkaPublisher
from pipeline.validation import validate
from pipeline.writer import OneLakeWriter
from shared.logging import log_context

log = logging.getLogger(__name__)


class ValidationFailed(Exception):
    """Raised inside the retry loop when ``validate()`` returns ``ok=False``.

    Gives validation failure a typed exception so the DLQ payload's
    ``error`` and ``stack_trace`` fields look the same as for
    writer/publisher exceptions.
    """


class Processor:
    """Per-event processor: validate → extract → envelope → write → publish.

    On any step's failure the call is retried up to ``max_retries`` times
    with exponential backoff. After exhaustion the raw event is published
    to ``propgateway.{source_name}.dlq`` as a flat DLQ payload.
    """

    def __init__(
        self,
        *,
        source_name: str,
        source_event_hub: str,
        pipeline_id: str,
        extractor: Callable[[dict[str, Any]], tuple[dict[str, Any], str]],
        required_fields: Iterable[str],
        writer: OneLakeWriter,
        publisher: KafkaPublisher,
        kafka_output_topic: str,
        max_retries: int = 3,
        backoff_base_s: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._source_name = source_name
        self._source_event_hub = source_event_hub
        self._pipeline_id = pipeline_id
        self._extractor = extractor
        self._required_fields = list(required_fields)
        self._writer = writer
        self._publisher = publisher
        self._kafka_output_topic = kafka_output_topic
        self._dlq_topic = f"propgateway.{source_name}.dlq"
        self._max_retries = max_retries
        self._backoff_base_s = backoff_base_s
        self._sleep = sleep

    def process(self, raw_event: Any, received_at: datetime) -> None:
        """Process one event end-to-end with retry/DLQ.

        Re-raises only if the DLQ publish itself fails; ordinary
        validation/extract/write/publish failures are absorbed into the
        DLQ path.
        """
        start = time.monotonic()
        correlation_id = _extract_correlation_id(raw_event)
        last_error: Exception | None = None

        with log_context(correlation_id=correlation_id, envelope_id=None):
            for attempt in range(self._max_retries + 1):
                try:
                    self._attempt(raw_event, received_at, retry_count=attempt)
                except Exception as exc:
                    last_error = exc
                    log.warning(
                        "processing attempt failed",
                        extra={
                            "attempt": attempt,
                            "max_retries": self._max_retries,
                            "error": str(exc),
                        },
                        exc_info=exc,
                    )
                    if attempt < self._max_retries:
                        self._sleep(self._backoff_base_s * (2 ** attempt))
                    continue
                self._record_outcome(start, status="success")
                log.info(
                    "event processed",
                    extra={"retry_count": attempt},
                )
                return

            assert last_error is not None
            try:
                self._send_to_dlq(
                    raw_event, last_error, retry_count=self._max_retries
                )
            finally:
                self._record_outcome(start, status="failure")

    def _attempt(
        self,
        raw_event: Any,
        received_at: datetime,
        *,
        retry_count: int,
    ) -> None:
        result = validate(raw_event, self._required_fields)
        if not result.ok:
            raise ValidationFailed(result.reason)

        metadata, event_type = self._extractor(raw_event)

        envelope = build_envelope(
            raw_event=raw_event,
            metadata=metadata,
            event_type=event_type,
            correlation_id=_extract_correlation_id(raw_event),
            source_system=self._source_name,
            source_event_hub=self._source_event_hub,
            source_original_timestamp=_extract_original_timestamp(raw_event),
            pipeline_id=self._pipeline_id,
            retry_count=retry_count,
            received_at=received_at,
        )

        with log_context(
            correlation_id=envelope["correlation_id"],
            envelope_id=envelope["envelope_id"],
        ):
            self._writer.add(envelope)
            self._publisher.publish(self._kafka_output_topic, envelope)

    def _send_to_dlq(
        self,
        raw_event: Any,
        error: Exception,
        *,
        retry_count: int,
    ) -> None:
        dlq_payload = {
            "raw_event": raw_event,
            "error": str(error),
            "stack_trace": "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            ),
            "retry_count": retry_count,
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._publisher.publish(self._dlq_topic, dlq_payload)
        except Exception:
            log.exception(
                "dlq publish failed",
                extra={"topic": self._dlq_topic, "retry_count": retry_count},
            )
            raise
        metrics.events_dlq_total.labels(source=self._source_name).inc()
        log.error(
            "event sent to dlq",
            extra={
                "topic": self._dlq_topic,
                "retry_count": retry_count,
                "error": str(error),
            },
        )

    def _record_outcome(self, start: float, *, status: str) -> None:
        duration = time.monotonic() - start
        metrics.processing_duration_seconds.labels(
            source=self._source_name
        ).observe(duration)
        metrics.events_processed_total.labels(
            source=self._source_name, status=status
        ).inc()


def _extract_correlation_id(raw_event: Any) -> str | None:
    """Best-effort extraction of a top-level ``correlation_id`` string."""
    if not isinstance(raw_event, dict):
        return None
    cid = raw_event.get("correlation_id")
    return cid if isinstance(cid, str) else None


def _extract_original_timestamp(raw_event: Any) -> str | None:
    """Best-effort extraction of a top-level ``timestamp`` string."""
    if not isinstance(raw_event, dict):
        return None
    ts = raw_event.get("timestamp")
    return ts if isinstance(ts, str) else None
