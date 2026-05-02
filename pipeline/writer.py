"""OneLake Parquet writer per PRD §Pipeline Components §5.

Buffers enveloped events in memory and flushes them to OneLake
(ADLS Gen2) as Parquet files on interval (default 60s) or size
threshold (default 1000 events) — whichever comes first, per PRD
§Scale & Performance.

Authenticates via ``DefaultAzureCredential``. The Parquet schema is
flat envelope columns plus JSON-string metadata/payload (ADR 0014).
The interval flush is driven by an internal daemon thread with a
buffer lock (ADR 0013); call ``start()`` / ``stop()`` to manage its
lifecycle.

SDK errors propagate from ``add()`` and ``flush()`` to the caller —
retry/DLQ is owned by issue 0010. The internal flusher thread logs
errors and keeps going so a transient OneLake hiccup does not
silently kill the writer; the next interval reattempts.
"""

from __future__ import annotations

import io
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from azure.identity import DefaultAzureCredential
from azure.storage.filedatalake import DataLakeServiceClient

from pipeline import metrics

log = logging.getLogger(__name__)

# Flat envelope columns + JSON for metadata/payload — see ADR 0014.
PARQUET_SCHEMA = pa.schema(
    [
        pa.field("envelope_id", pa.string()),
        pa.field("correlation_id", pa.string()),
        pa.field("schema_version", pa.string()),
        pa.field("source_system", pa.string()),
        pa.field("source_event_hub", pa.string()),
        pa.field("source_original_timestamp", pa.string()),
        pa.field("event_type", pa.string()),
        pa.field("event_received_at", pa.string()),
        pa.field("event_processed_at", pa.string()),
        pa.field("pipeline_id", pa.string()),
        pa.field("retry_count", pa.int64()),
        pa.field("processing_ms", pa.int64()),
        pa.field("metadata_json", pa.string()),
        pa.field("payload_json", pa.string()),
    ]
)


class OneLakeWriter:
    """Thread-safe buffered Parquet writer for OneLake.

    Size-triggered flushes happen synchronously inside ``add()``.
    Interval-triggered flushes run from a daemon thread started by
    ``start()``. Call ``stop()`` on shutdown to halt the thread and
    drain the buffer.
    """

    def __init__(
        self,
        *,
        account_url: str,
        filesystem: str,
        lakehouse_path: str,
        source_name: str,
        flush_interval_s: float = 60.0,
        flush_size: int = 1000,
        credential: Any | None = None,
    ) -> None:
        self._account_url = account_url
        self._filesystem = filesystem
        self._lakehouse_path = lakehouse_path.rstrip("/")
        self._source_name = source_name
        self._flush_interval_s = flush_interval_s
        self._flush_size = flush_size
        self._credential = credential if credential is not None else DefaultAzureCredential()

        self._service_client = DataLakeServiceClient(
            account_url=account_url,
            credential=self._credential,
        )
        self._fs_client = self._service_client.get_file_system_client(filesystem)

        self._buffer: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._flusher: threading.Thread | None = None

    def add(self, envelope: dict[str, Any]) -> None:
        """Append an envelope; trigger a synchronous flush at the size threshold."""
        with self._lock:
            self._buffer.append(envelope)
            current_size = len(self._buffer)
        metrics.buffer_size.labels(source=self._source_name).set(current_size)
        if current_size >= self._flush_size:
            self.flush()

    def flush(self) -> None:
        """Drain the buffer to a single Parquet file in OneLake.

        No-op when the buffer is empty. Errors from the SDK propagate.
        """
        with self._lock:
            if not self._buffer:
                return
            batch = self._buffer
            self._buffer = []
        metrics.buffer_size.labels(source=self._source_name).set(0)

        batch_id = uuid.uuid4().hex[:12]
        path = self._build_path(batch_id)
        log.info(
            "writer flush starting",
            extra={"batch_id": batch_id, "batch_size": len(batch), "path": path},
        )
        start = time.monotonic()
        try:
            self._upload(path, batch)
        except Exception:
            log.exception(
                "writer flush failed",
                extra={"batch_id": batch_id, "batch_size": len(batch), "path": path},
            )
            raise
        duration = time.monotonic() - start
        metrics.batch_write_duration_seconds.labels(source=self._source_name).observe(duration)
        metrics.batch_size.labels(source=self._source_name).observe(len(batch))
        log.info(
            "writer flush succeeded",
            extra={
                "batch_id": batch_id,
                "batch_size": len(batch),
                "path": path,
                "duration_s": duration,
            },
        )

    def start(self) -> None:
        """Start the interval flusher thread. A second call while running is a no-op."""
        if self._flusher is not None and self._flusher.is_alive():
            return
        self._stop_event.clear()
        self._flusher = threading.Thread(
            target=self._run_flusher,
            name=f"propgateway-writer-flusher-{self._source_name}",
            daemon=True,
        )
        self._flusher.start()

    def stop(self) -> None:
        """Stop the flusher thread and drain the buffer."""
        self._stop_event.set()
        if self._flusher is not None:
            self._flusher.join()
            self._flusher = None
        self.flush()

    def _run_flusher(self) -> None:
        while not self._stop_event.wait(self._flush_interval_s):
            try:
                self.flush()
            except Exception:
                # The interval thread has no caller to surface to; logging and
                # continuing keeps the next interval available for retry.
                # add() and flush() still raise to their callers — that is
                # where issue 0010's retry policy attaches.
                log.exception("interval flush failed; continuing")

    def _build_path(self, batch_id: str) -> str:
        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y%m%dT%H%M%S")
        return (
            f"{self._lakehouse_path}/{self._source_name}/"
            f"{now.year:04d}/{now.month:02d}/{now.day:02d}/"
            f"{ts}_{batch_id}.parquet"
        )

    def _upload(self, path: str, batch: list[dict[str, Any]]) -> None:
        data = _serialise_parquet(batch)
        file_client = self._fs_client.get_file_client(path)
        file_client.upload_data(data, overwrite=True)


def _serialise_parquet(batch: list[dict[str, Any]]) -> bytes:
    """Serialise a list of envelopes to Parquet bytes per ADR 0014."""
    columns: dict[str, list[Any]] = {field.name: [] for field in PARQUET_SCHEMA}
    for env in batch:
        source = env.get("source") or {}
        event = env.get("event") or {}
        pipeline_block = env.get("pipeline") or {}
        columns["envelope_id"].append(env.get("envelope_id"))
        columns["correlation_id"].append(env.get("correlation_id"))
        columns["schema_version"].append(env.get("schema_version"))
        columns["source_system"].append(source.get("system"))
        columns["source_event_hub"].append(source.get("event_hub"))
        columns["source_original_timestamp"].append(source.get("original_timestamp"))
        columns["event_type"].append(event.get("type"))
        columns["event_received_at"].append(event.get("received_at"))
        columns["event_processed_at"].append(event.get("processed_at"))
        columns["pipeline_id"].append(pipeline_block.get("pipeline_id"))
        columns["retry_count"].append(pipeline_block.get("retry_count"))
        columns["processing_ms"].append(pipeline_block.get("processing_ms"))
        columns["metadata_json"].append(json.dumps(env.get("metadata"), default=str))
        columns["payload_json"].append(json.dumps(env.get("payload"), default=str))
    table = pa.Table.from_pydict(columns, schema=PARQUET_SCHEMA)
    sink = io.BytesIO()
    pq.write_table(table, sink)
    return sink.getvalue()
