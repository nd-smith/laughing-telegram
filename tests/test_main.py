"""Tests for the worker entry point ``pipeline.__main__``.

The whole module is exercised with everything below it mocked: source
loading, the four component classes, the metrics HTTP server, and
``setup_logging``. The aim is purely wiring — these tests do not use a
real Event Hub, OneLake, or Kafka.
"""

from __future__ import annotations

import signal
import sys
import threading
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from pipeline import __main__ as main_module


REQUIRED_ENV = {
    "PROPGATEWAY_PIPELINE_ID": "worker-test",
    "PROPGATEWAY_METRICS_PORT": "9001",
    "PROPGATEWAY_CONSUMER_GROUP": "$Default",
    "PROPGATEWAY_CHECKPOINT_STORE_URL": "https://chk.blob.core.windows.net",
    "PROPGATEWAY_CHECKPOINT_CONTAINER": "checkpoints",
    "PROPGATEWAY_ONELAKE_ACCOUNT_URL": "https://onelake.dfs.fabric.microsoft.com",
    "PROPGATEWAY_ONELAKE_FILESYSTEM": "ws-prop",
    "PROPGATEWAY_LAKEHOUSE_PATH": "Files/landing",
    "PROPGATEWAY_KAFKA_BOOTSTRAP_SERVERS": "kafka-1:9092,kafka-2:9092",
}


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in REQUIRED_ENV.items():
        monkeypatch.setenv(k, v)


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main_module.main(["--help"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "--source" in captured.out


def test_missing_source_exits_nonzero_with_clear_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main_module.main([])
    assert excinfo.value.code != 0
    captured = capsys.readouterr()
    assert "--source" in captured.err


def test_nonexistent_source_returns_nonzero_and_message_references_load_source(
    env: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch.object(main_module, "setup_logging"), patch.object(
        main_module, "start_metrics_server"
    ), patch.object(
        main_module,
        "load_source",
        side_effect=ModuleNotFoundError(
            "No module named 'pipeline.sources.definitely_not_real'"
        ),
    ):
        rc = main_module.main(["--source", "definitely_not_real"])

    assert rc != 0
    err = capsys.readouterr().err
    assert "load_source" in err
    assert "definitely_not_real" in err


def test_signal_handler_invocation_triggers_writer_stop_then_publisher_flush(
    env: None,
) -> None:
    """SIGTERM handler sets the shutdown event; once consumer.run returns,
    the writer is drained before the publisher is flushed."""
    captured_handlers: dict[int, Any] = {}

    def fake_signal(signum: int, handler: Any) -> Any:
        captured_handlers[signum] = handler
        return None

    source_module = MagicMock(name="source_module")
    source_module.SOURCE_NAME = "source-x"
    source_module.EVENT_HUB_NAMESPACE = "ns.servicebus.windows.net"
    source_module.EVENT_HUB_NAME = "source-x-events"
    source_module.KAFKA_OUTPUT_TOPIC = "propgateway.source-x"
    source_module.REQUIRED_FIELDS = ("data",)
    source_module.extract = MagicMock(return_value=({}, "status_update"))

    parent = MagicMock(name="parent")

    consumer_instance = MagicMock(name="consumer_instance")
    writer_instance = MagicMock(name="writer_instance")
    publisher_instance = MagicMock(name="publisher_instance")
    processor_instance = MagicMock(name="processor_instance")

    parent.attach_mock(consumer_instance, "consumer")
    parent.attach_mock(writer_instance, "writer")
    parent.attach_mock(publisher_instance, "publisher")

    def consumer_run(on_event: Any, shutdown: threading.Event) -> None:
        # Simulate a SIGTERM arriving mid-run by invoking the captured
        # handler. The handler must set the shutdown event.
        handler = captured_handlers[signal.SIGTERM]
        handler(signal.SIGTERM, None)
        assert shutdown.is_set()
        # ``run`` returns once the SDK's ``receive`` would have returned.

    consumer_instance.run.side_effect = consumer_run

    with patch.object(main_module, "signal") as signal_mod, patch.object(
        main_module, "setup_logging"
    ), patch.object(main_module, "start_metrics_server"), patch.object(
        main_module, "load_source", return_value=source_module
    ), patch.object(
        main_module, "EventHubConsumer", return_value=consumer_instance
    ), patch.object(
        main_module, "OneLakeWriter", return_value=writer_instance
    ), patch.object(
        main_module, "KafkaPublisher", return_value=publisher_instance
    ), patch.object(
        main_module, "Processor", return_value=processor_instance
    ):
        signal_mod.signal.side_effect = fake_signal
        signal_mod.SIGTERM = signal.SIGTERM
        signal_mod.SIGINT = signal.SIGINT

        rc = main_module.main(["--source", "source-x"])

    assert rc == 0
    assert signal.SIGTERM in captured_handlers
    assert signal.SIGINT in captured_handlers

    # The shutdown sequence must be: writer.stop() -> publisher.flush(...).
    # ``parent.mock_calls`` records calls across attached child mocks in order.
    names_in_order = [c[0] for c in parent.mock_calls]
    assert "writer.stop" in names_in_order
    assert "publisher.flush" in names_in_order
    assert names_in_order.index("writer.stop") < names_in_order.index(
        "publisher.flush"
    )

    publisher_instance.flush.assert_called_once_with(
        main_module.PUBLISHER_SHUTDOWN_FLUSH_TIMEOUT_S
    )


def test_on_event_passes_parsed_json_to_processor() -> None:
    processor = MagicMock(name="processor")
    on_event = main_module._make_on_event(processor)

    fake_event = MagicMock()
    fake_event.body_as_json.return_value = {"data": {"k": "v"}}

    on_event(fake_event)

    assert processor.process.call_count == 1
    raw_event_arg, received_at_arg = processor.process.call_args.args
    assert raw_event_arg == {"data": {"k": "v"}}
    assert received_at_arg.tzinfo is not None


def test_on_event_falls_back_to_str_when_json_parse_fails() -> None:
    processor = MagicMock(name="processor")
    on_event = main_module._make_on_event(processor)

    fake_event = MagicMock()
    fake_event.body_as_json.side_effect = ValueError("not json")
    fake_event.body_as_str.return_value = "not-json-bytes"

    on_event(fake_event)

    raw_event_arg, _ = processor.process.call_args.args
    # Non-dict input is what we want — the validator will reject it and
    # the retry/DLQ path will handle the failure (see ADR 0021).
    assert raw_event_arg == "not-json-bytes"
