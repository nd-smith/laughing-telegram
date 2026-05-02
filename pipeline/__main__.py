"""PropGateway worker entry point per PRD §Pipeline Components §1.

Run with::

    python -m pipeline --source <source-name>

One worker process serves exactly one source. ``<source-name>`` must
match a Python module under ``pipeline/sources/`` (see
``pipeline/sources/__init__.py``).

Configuration — environment variables
-------------------------------------

All values are read once at startup. Required variables raise
``KeyError`` with the variable name when missing — this is deliberate;
the docstring is the configuration spec, not a schema library.

Required:

- ``PROPGATEWAY_PIPELINE_ID`` — identifier for this worker instance,
  written to ``envelope.pipeline.pipeline_id``.
- ``PROPGATEWAY_METRICS_PORT`` — Prometheus scrape port (int).
- ``PROPGATEWAY_CONSUMER_GROUP`` — Event Hub consumer group name.
- ``PROPGATEWAY_CHECKPOINT_STORE_URL`` — Azure Blob account URL backing
  the Event Hub checkpoint store.
- ``PROPGATEWAY_CHECKPOINT_CONTAINER`` — Blob container name within the
  checkpoint store.
- ``PROPGATEWAY_ONELAKE_ACCOUNT_URL`` — ADLS Gen2 account URL for the
  OneLake writer.
- ``PROPGATEWAY_ONELAKE_FILESYSTEM`` — file system (container) name in
  that account.
- ``PROPGATEWAY_LAKEHOUSE_PATH`` — base path inside the file system
  beneath which Parquet batches land
  (``<lakehouse_path>/<source>/YYYY/MM/DD/...``).
- ``PROPGATEWAY_KAFKA_BOOTSTRAP_SERVERS`` — comma-separated Kafka
  bootstrap servers, passed verbatim into
  ``producer_config["bootstrap.servers"]``.

Optional:

- ``PROPGATEWAY_LOG_LEVEL`` — root log level. Default ``INFO``.
- ``PROPGATEWAY_EVENTHUB_NAMESPACE`` — overrides the source module's
  ``EVENT_HUB_NAMESPACE``. Useful for staging/test environments.

Shutdown
--------

The process installs ``SIGTERM`` and ``SIGINT`` handlers that set a
shared ``threading.Event``. ``EventHubConsumer.run`` watches that flag
on a daemon thread and closes its underlying client (ADR 0012). When
``run`` returns, the entry point drains the writer
(``OneLakeWriter.stop``) and flushes the publisher
(``KafkaPublisher.flush``) before exiting.

Bad-JSON events
---------------

When ``EventData.body_as_json()`` raises, the entry point falls back to
``body_as_str()`` and hands the raw string to the processor. The
processor's validator rejects non-dict input, the retry loop runs to
exhaustion, and the event lands in the source's DLQ topic. See ADR 0021.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from types import FrameType, ModuleType
from typing import Any, Callable, Sequence

from pipeline.consumer import EventHubConsumer
from pipeline.metrics import start_metrics_server
from pipeline.processor import Processor
from pipeline.publisher import KafkaPublisher
from pipeline.sources import load_source
from pipeline.writer import OneLakeWriter
from shared.logging import setup_logging

log = logging.getLogger(__name__)

PUBLISHER_SHUTDOWN_FLUSH_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class WorkerConfig:
    pipeline_id: str
    metrics_port: int
    consumer_group: str
    checkpoint_store_url: str
    checkpoint_container: str
    onelake_account_url: str
    onelake_filesystem: str
    lakehouse_path: str
    kafka_bootstrap_servers: str
    log_level: str
    eventhub_namespace_override: str | None


@dataclass(frozen=True)
class WorkerComponents:
    consumer: EventHubConsumer
    writer: OneLakeWriter
    publisher: KafkaPublisher
    processor: Processor


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns the worker exit code."""
    args = _parse_args(argv)
    config = _read_config()

    setup_logging(source=args.source, level=config.log_level)
    start_metrics_server(port=config.metrics_port)

    try:
        source_module = load_source(args.source)
    except ModuleNotFoundError as exc:
        message = (
            f"unknown source {args.source!r}: load_source could not import "
            f"pipeline.sources.{args.source} ({exc})"
        )
        print(message, file=sys.stderr)
        log.error(message)
        return 2

    components = _build_components(source_module, config)
    return _run(components)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m pipeline",
        description=(
            "PropGateway worker. Consumes from an Azure Event Hub for one "
            "source, writes Parquet batches to OneLake, and publishes "
            "envelopes to Kafka. See module docstring for the full env-var "
            "configuration spec."
        ),
    )
    parser.add_argument(
        "--source",
        required=True,
        help=(
            "Source name. Must match a Python module under pipeline/sources/ "
            "(e.g. 'source-a' for pipeline/sources/source_a.py — the loader "
            "uses the value verbatim as the import suffix)."
        ),
    )
    return parser.parse_args(argv)


def _read_config() -> WorkerConfig:
    return WorkerConfig(
        pipeline_id=_require_env("PROPGATEWAY_PIPELINE_ID"),
        metrics_port=int(_require_env("PROPGATEWAY_METRICS_PORT")),
        consumer_group=_require_env("PROPGATEWAY_CONSUMER_GROUP"),
        checkpoint_store_url=_require_env("PROPGATEWAY_CHECKPOINT_STORE_URL"),
        checkpoint_container=_require_env("PROPGATEWAY_CHECKPOINT_CONTAINER"),
        onelake_account_url=_require_env("PROPGATEWAY_ONELAKE_ACCOUNT_URL"),
        onelake_filesystem=_require_env("PROPGATEWAY_ONELAKE_FILESYSTEM"),
        lakehouse_path=_require_env("PROPGATEWAY_LAKEHOUSE_PATH"),
        kafka_bootstrap_servers=_require_env("PROPGATEWAY_KAFKA_BOOTSTRAP_SERVERS"),
        log_level=os.environ.get("PROPGATEWAY_LOG_LEVEL", "INFO"),
        eventhub_namespace_override=os.environ.get("PROPGATEWAY_EVENTHUB_NAMESPACE"),
    )


def _require_env(name: str) -> str:
    try:
        return os.environ[name]
    except KeyError as exc:
        raise KeyError(
            f"required environment variable {name!r} is not set"
        ) from exc


def _build_components(
    source_module: ModuleType, config: WorkerConfig
) -> WorkerComponents:
    eventhub_namespace = (
        config.eventhub_namespace_override or source_module.EVENT_HUB_NAMESPACE
    )
    consumer = EventHubConsumer(
        eventhub_namespace=eventhub_namespace,
        eventhub_name=source_module.EVENT_HUB_NAME,
        consumer_group=config.consumer_group,
        checkpoint_store_url=config.checkpoint_store_url,
        checkpoint_container=config.checkpoint_container,
        source_name=source_module.SOURCE_NAME,
    )
    writer = OneLakeWriter(
        account_url=config.onelake_account_url,
        filesystem=config.onelake_filesystem,
        lakehouse_path=config.lakehouse_path,
        source_name=source_module.SOURCE_NAME,
    )
    publisher = KafkaPublisher(
        producer_config={"bootstrap.servers": config.kafka_bootstrap_servers},
        source_name=source_module.SOURCE_NAME,
    )
    processor = Processor(
        source_name=source_module.SOURCE_NAME,
        source_event_hub=source_module.EVENT_HUB_NAME,
        pipeline_id=config.pipeline_id,
        extractor=source_module.extract,
        required_fields=source_module.REQUIRED_FIELDS,
        writer=writer,
        publisher=publisher,
        kafka_output_topic=source_module.KAFKA_OUTPUT_TOPIC,
    )
    return WorkerComponents(
        consumer=consumer, writer=writer, publisher=publisher, processor=processor
    )


def _run(components: WorkerComponents) -> int:
    shutdown_event = threading.Event()
    _install_signal_handlers(shutdown_event)

    on_event = _make_on_event(components.processor)

    components.writer.start()
    try:
        components.consumer.run(on_event, shutdown_event)
    finally:
        log.info("shutdown: stopping writer (drain buffer)")
        components.writer.stop()
        log.info("shutdown: flushing publisher")
        components.publisher.flush(PUBLISHER_SHUTDOWN_FLUSH_TIMEOUT_S)
        log.info("shutdown complete")
    return 0


def _install_signal_handlers(shutdown_event: threading.Event) -> None:
    def _handle(signum: int, _frame: FrameType | None) -> None:
        log.info("signal received; shutting down", extra={"signum": signum})
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)


def _make_on_event(processor: Processor) -> Callable[[Any], None]:
    def on_event(event: Any) -> None:
        received_at = datetime.now(timezone.utc)
        try:
            raw_event: Any = event.body_as_json()
        except Exception:
            log.warning(
                "event body is not valid JSON; routing to DLQ via validator rejection",
                exc_info=True,
            )
            try:
                raw_event = event.body_as_str()
            except Exception:
                raw_event = repr(getattr(event, "body", event))
        processor.process(raw_event, received_at)

    return on_event


if __name__ == "__main__":
    sys.exit(main())
