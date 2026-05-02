"""Sync Event Hub consumer per PRD §Pipeline Components §2.

Wraps `azure.eventhub.EventHubConsumerClient` (sync) with the sync
`BlobCheckpointStore` from `azure.eventhub.extensions.checkpointstoreblob`.
Authenticates via `DefaultAzureCredential` — no connection strings, no
SAS tokens.

The consumer delivers one event at a time to a caller-supplied callback
(see ADR 0011) and only checkpoints the partition after that callback
returns without raising. Graceful shutdown is driven by a
``threading.Event`` supplied by the worker entry point (see ADR 0012):
when set, an internal watcher thread calls ``client.close()`` to break
the blocking ``receive()`` loop.

Retry / DLQ semantics are out of scope here — see issue 0010. If the
callback raises, this module logs the failure, leaves the checkpoint
unchanged, and continues consuming subsequent events.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from azure.eventhub import EventHubConsumerClient
from azure.eventhub.extensions.checkpointstoreblob import BlobCheckpointStore
from azure.identity import DefaultAzureCredential

from pipeline import metrics

log = logging.getLogger(__name__)

EventCallback = Callable[[Any], None]


class EventHubConsumer:
    """Sync Event Hub consumer with after-success checkpointing."""

    def __init__(
        self,
        *,
        eventhub_namespace: str,
        eventhub_name: str,
        consumer_group: str,
        checkpoint_store_url: str,
        checkpoint_container: str,
        source_name: str,
        credential: Any | None = None,
    ) -> None:
        self._eventhub_namespace = eventhub_namespace
        self._eventhub_name = eventhub_name
        self._consumer_group = consumer_group
        self._source_name = source_name
        self._credential = credential if credential is not None else DefaultAzureCredential()

        self._checkpoint_store = BlobCheckpointStore(
            blob_account_url=checkpoint_store_url,
            container_name=checkpoint_container,
            credential=self._credential,
        )
        self._client = EventHubConsumerClient(
            fully_qualified_namespace=eventhub_namespace,
            eventhub_name=eventhub_name,
            consumer_group=consumer_group,
            credential=self._credential,
            checkpoint_store=self._checkpoint_store,
        )

    def run(self, callback: EventCallback, shutdown: threading.Event) -> None:
        """Consume events and invoke ``callback`` per event, blocking until shutdown.

        The caller (worker entry point, issue 0011) installs SIGTERM/SIGINT
        handlers and sets ``shutdown`` when the worker should exit. An
        internal watcher thread observes the flag and calls ``close()`` on
        the underlying client, which returns control from ``receive()``.
        """
        log.info(
            "event hub consumer connecting",
            extra={
                "eventhub_namespace": self._eventhub_namespace,
                "eventhub_name": self._eventhub_name,
                "consumer_group": self._consumer_group,
            },
        )

        watcher = threading.Thread(
            target=self._watch_for_shutdown,
            args=(shutdown,),
            name="propgateway-consumer-shutdown-watcher",
            daemon=True,
        )
        watcher.start()

        try:
            self._client.receive(on_event=self._make_on_event(callback))
        finally:
            shutdown.set()
            watcher.join()
            log.info("event hub consumer disconnected")

    def close(self) -> None:
        """Close the underlying client. Safe to call from any thread."""
        self._client.close()

    def _make_on_event(self, callback: EventCallback) -> Callable[[Any, Any], None]:
        source = self._source_name

        def on_event(partition_context: Any, event: Any) -> None:
            if event is None:
                return
            metrics.events_received_total.labels(source=source).inc()
            log.debug(
                "event received",
                extra={"partition_id": partition_context.partition_id},
            )
            try:
                callback(event)
            except Exception:
                log.exception(
                    "callback raised; skipping checkpoint",
                    extra={"partition_id": partition_context.partition_id},
                )
                return
            partition_context.update_checkpoint(event)
            log.debug(
                "checkpoint updated",
                extra={"partition_id": partition_context.partition_id},
            )

        return on_event

    def _watch_for_shutdown(self, shutdown: threading.Event) -> None:
        shutdown.wait()
        log.info("shutdown flag set; closing event hub client")
        self._client.close()
