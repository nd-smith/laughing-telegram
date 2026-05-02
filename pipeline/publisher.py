"""Kafka publisher per PRD §Pipeline Components §6.

Wraps ``confluent_kafka.Producer`` with synchronous publish semantics
(ADR 0015): each ``publish()`` call queues exactly one message via
``produce()`` and then calls ``producer.flush(timeout)``, which blocks
until the per-message ``on_delivery`` callback fires. The callback
records ``kafka_publish_duration_seconds``, logs the outcome, and
stashes any broker error in a closure-local dict; ``publish()`` then
either returns or raises ``PublishError`` so the caller (issue 0010)
can route to retry/DLQ.

JSON serialisation is strict (ADR 0016): the publisher calls
``json.dumps(envelope).encode("utf-8")`` with no ``default=`` encoder.
``pipeline/envelope.py`` owns conversion of non-JSON-native values
(UUIDs, datetimes) before envelopes reach the publisher. Note the
deliberate asymmetry with ``pipeline/writer.py``, which uses
``default=str`` for the variable, externally-shaped ``metadata`` and
``payload`` blocks.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from confluent_kafka import Producer

from pipeline import metrics

log = logging.getLogger(__name__)


class PublishError(Exception):
    """Delivery report indicated failure, or flush timed out before completion.

    Issue 0010 catches this single class to drive retry/DLQ. Both broker
    failure and flush timeout map here because the retry policy is the
    same for both.
    """


class KafkaPublisher:
    """Synchronous Kafka publisher wrapping ``confluent_kafka.Producer``."""

    def __init__(
        self,
        *,
        producer_config: dict[str, Any],
        source_name: str,
        flush_timeout_s: float = 30.0,
        producer: Producer | None = None,
    ) -> None:
        self._source_name = source_name
        self._flush_timeout_s = flush_timeout_s
        self._producer = producer if producer is not None else Producer(producer_config)

    def publish(self, topic: str, envelope: dict[str, Any]) -> None:
        """Publish ``envelope`` to ``topic``, blocking until the delivery report.

        Raises ``PublishError`` on broker failure or flush timeout.
        Raises ``TypeError`` from ``json.dumps`` if the envelope contains
        a non-JSON-native value (ADR 0016).
        """
        payload = json.dumps(envelope).encode("utf-8")
        delivery: dict[str, Any] = {"err": None, "done": False}
        start = time.monotonic()

        def on_delivery(err: Any, msg: Any) -> None:
            duration = time.monotonic() - start
            metrics.kafka_publish_duration_seconds.labels(source=self._source_name).observe(duration)
            delivery["done"] = True
            if err is not None:
                delivery["err"] = err
                log.error(
                    "kafka publish failed",
                    extra={"topic": topic, "error": str(err)},
                )
                return
            log.debug(
                "kafka publish succeeded",
                extra={
                    "topic": topic,
                    "partition": msg.partition(),
                    "offset": msg.offset(),
                },
            )

        self._producer.produce(topic, value=payload, on_delivery=on_delivery)
        remaining = self._producer.flush(self._flush_timeout_s)

        if remaining > 0 or not delivery["done"]:
            raise PublishError(
                f"kafka publish to {topic!r} did not complete within "
                f"{self._flush_timeout_s}s"
            )
        if delivery["err"] is not None:
            raise PublishError(
                f"kafka publish to {topic!r} failed: {delivery['err']}"
            )

    def flush(self, timeout_s: float) -> None:
        """Drain the producer queue. Called by the entry point on shutdown."""
        remaining = self._producer.flush(timeout_s)
        if remaining > 0:
            log.warning(
                "kafka publisher flush left messages in queue",
                extra={"remaining": remaining, "timeout_s": timeout_s},
            )
