"""Tests for pipeline.writer.

The Azure SDK is mocked at the module boundary: ``DataLakeServiceClient``
and ``DefaultAzureCredential`` are patched in ``pipeline.writer`` so no
network I/O is attempted. Path formatting and Parquet serialisation are
exercised against the real implementations — only the ADLS upload call
is faked.
"""

from __future__ import annotations

import io
import json
import re
import threading
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pyarrow.parquet as pq
import pytest

from pipeline import metrics
from pipeline import writer as writer_module


def _make_writer(
    *,
    flush_interval_s: float = 60.0,
    flush_size: int = 1000,
    source_name: str = "source-a",
) -> tuple[writer_module.OneLakeWriter, MagicMock, MagicMock]:
    """Build an OneLakeWriter with the SDK fully mocked.

    Returns ``(writer, file_system_client_mock, file_client_mock)``. The
    ``file_client_mock`` is what ``upload_data`` is called against, so
    tests assert against it directly.
    """
    file_client = MagicMock(name="file_client")
    fs_client = MagicMock(name="fs_client")
    fs_client.get_file_client.return_value = file_client
    service_client = MagicMock(name="service_client")
    service_client.get_file_system_client.return_value = fs_client

    with patch.object(
        writer_module, "DataLakeServiceClient", return_value=service_client
    ) as svc_cls, patch.object(writer_module, "DefaultAzureCredential") as cred_cls:
        cred_cls.return_value = MagicMock(name="credential")
        w = writer_module.OneLakeWriter(
            account_url="https://onelake.dfs.fabric.microsoft.com",
            filesystem="prop-workspace",
            lakehouse_path="propgateway.Lakehouse/Files",
            source_name=source_name,
            flush_interval_s=flush_interval_s,
            flush_size=flush_size,
        )
        w._test_svc_cls = svc_cls
    return w, fs_client, file_client


def _envelope(envelope_id: str = "e-1", correlation_id: str | None = "c-1") -> dict:
    return {
        "envelope_id": envelope_id,
        "correlation_id": correlation_id,
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
        "payload": {"raw": "anything"},
    }


def _buffer_size(source: str) -> float:
    return metrics.buffer_size.labels(source=source)._value.get()


def test_constructor_wires_sdk_with_credential():
    w, fs_client, _ = _make_writer()
    w._test_svc_cls.assert_called_once()
    kwargs = w._test_svc_cls.call_args.kwargs
    assert kwargs["account_url"] == "https://onelake.dfs.fabric.microsoft.com"
    assert kwargs["credential"] is w._credential
    w._service_client.get_file_system_client.assert_called_once_with("prop-workspace")


def test_size_triggered_flush_at_threshold():
    w, fs_client, file_client = _make_writer(flush_size=3)
    for i in range(2):
        w.add(_envelope(envelope_id=f"e-{i}"))
    file_client.upload_data.assert_not_called()

    w.add(_envelope(envelope_id="e-2"))

    file_client.upload_data.assert_called_once()
    fs_client.get_file_client.assert_called_once()
    assert _buffer_size("source-a") == 0


def test_interval_triggered_flush_drains_after_elapsed_time():
    w, _, file_client = _make_writer(flush_interval_s=0.05, flush_size=1000)
    w.add(_envelope())
    w.start()
    try:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if file_client.upload_data.called:
                break
            time.sleep(0.02)
    finally:
        w.stop()

    assert file_client.upload_data.called, "interval flush did not fire"


def test_path_format_matches_convention():
    w, fs_client, _ = _make_writer(flush_size=1)
    fixed_now = datetime(2026, 5, 2, 17, 8, 42, tzinfo=timezone.utc)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    with patch.object(writer_module, "datetime", _FixedDatetime):
        w.add(_envelope())

    fs_client.get_file_client.assert_called_once()
    path = fs_client.get_file_client.call_args.args[0]
    pattern = (
        r"^propgateway\.Lakehouse/Files/source-a/"
        r"2026/05/02/"
        r"20260502T170842_[0-9a-f]{12}\.parquet$"
    )
    assert re.match(pattern, path), f"path does not match convention: {path}"


def test_path_uses_provided_lakehouse_path_and_source():
    w, fs_client, _ = _make_writer(flush_size=1, source_name="source-b")
    w._lakehouse_path = "alt.Lakehouse/Files"

    w.add(_envelope())

    path = fs_client.get_file_client.call_args.args[0]
    assert path.startswith("alt.Lakehouse/Files/source-b/")


def test_lakehouse_path_trailing_slash_is_normalised():
    file_client = MagicMock()
    fs_client = MagicMock()
    fs_client.get_file_client.return_value = file_client
    service_client = MagicMock()
    service_client.get_file_system_client.return_value = fs_client
    with patch.object(writer_module, "DataLakeServiceClient", return_value=service_client), \
         patch.object(writer_module, "DefaultAzureCredential"):
        w = writer_module.OneLakeWriter(
            account_url="https://onelake.dfs.fabric.microsoft.com",
            filesystem="ws",
            lakehouse_path="propgateway.Lakehouse/Files/",
            source_name="source-a",
            flush_size=1,
        )
    w.add(_envelope())
    path = fs_client.get_file_client.call_args.args[0]
    assert "//" not in path


def test_sdk_error_surfaces_to_caller():
    w, _, file_client = _make_writer(flush_size=1)
    file_client.upload_data.side_effect = RuntimeError("ADLS exploded")

    with pytest.raises(RuntimeError, match="ADLS exploded"):
        w.add(_envelope())


def test_flush_drains_buffer_and_resets_state():
    w, _, file_client = _make_writer(flush_size=1000)
    for i in range(5):
        w.add(_envelope(envelope_id=f"e-{i}"))
    assert _buffer_size("source-a") == 5
    file_client.upload_data.assert_not_called()

    w.flush()

    file_client.upload_data.assert_called_once()
    assert _buffer_size("source-a") == 0

    file_client.upload_data.reset_mock()
    w.flush()
    file_client.upload_data.assert_not_called()


def test_flush_on_empty_buffer_is_noop():
    w, _, file_client = _make_writer()
    w.flush()
    file_client.upload_data.assert_not_called()


def test_parquet_payload_uses_flat_schema_with_json_blobs():
    """Verify the bytes uploaded match the schema declared in ADR 0014."""
    w, _, file_client = _make_writer(flush_size=2)
    captured: dict[str, bytes] = {}

    def capture(data, overwrite):
        captured["bytes"] = data

    file_client.upload_data.side_effect = capture
    w.add(_envelope(envelope_id="e-0", correlation_id="c-0"))
    w.add(_envelope(envelope_id="e-1", correlation_id=None))

    table = pq.read_table(io.BytesIO(captured["bytes"]))
    assert table.schema.equals(writer_module.PARQUET_SCHEMA)
    assert table.column("envelope_id").to_pylist() == ["e-0", "e-1"]
    assert table.column("correlation_id").to_pylist() == ["c-0", None]
    assert table.column("source_system").to_pylist() == ["source-a", "source-a"]
    assert table.column("retry_count").to_pylist() == [0, 0]
    metadata = [json.loads(s) for s in table.column("metadata_json").to_pylist()]
    assert metadata == [
        {"policy_id": "P-123", "status": "active"},
        {"policy_id": "P-123", "status": "active"},
    ]
    payloads = [json.loads(s) for s in table.column("payload_json").to_pylist()]
    assert payloads == [{"raw": "anything"}, {"raw": "anything"}]


def test_interval_thread_swallows_errors_and_keeps_running():
    """A failed interval flush must not kill the thread; the next interval retries."""
    w, _, file_client = _make_writer(flush_interval_s=0.05, flush_size=1000)
    file_client.upload_data.side_effect = [RuntimeError("transient"), None]

    w.add(_envelope(envelope_id="e-0"))
    w.start()
    try:
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if file_client.upload_data.call_count >= 1:
                w.add(_envelope(envelope_id="e-1"))
                break
            time.sleep(0.02)
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if file_client.upload_data.call_count >= 2:
                break
            time.sleep(0.02)
    finally:
        w.stop()

    assert file_client.upload_data.call_count >= 2


def test_stop_drains_remaining_buffer():
    w, _, file_client = _make_writer(flush_interval_s=60.0, flush_size=1000)
    w.start()
    w.add(_envelope())
    w.stop()
    file_client.upload_data.assert_called_once()


def test_buffer_size_gauge_tracks_add_and_flush():
    w, _, _ = _make_writer(flush_size=1000, source_name="source-gauge")
    w.add(_envelope())
    w.add(_envelope())
    assert _buffer_size("source-gauge") == 2
    w.flush()
    assert _buffer_size("source-gauge") == 0


def test_concurrent_adds_do_not_lose_events():
    """Sanity check on the buffer lock under threading."""
    w, _, file_client = _make_writer(flush_size=10_000)

    def worker():
        for i in range(100):
            w.add(_envelope(envelope_id=f"e-{threading.get_ident()}-{i}"))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    captured: dict[str, bytes] = {}

    def capture(data, overwrite):
        captured["bytes"] = data

    file_client.upload_data.side_effect = capture
    w.flush()
    table = pq.read_table(io.BytesIO(captured["bytes"]))
    assert table.num_rows == 8 * 100
