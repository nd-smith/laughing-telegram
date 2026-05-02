"""Tests for pipeline.consumer.

The Azure SDK is mocked at the module boundary: ``EventHubConsumerClient``
and ``BlobCheckpointStore`` are patched in ``pipeline.consumer`` so no
network I/O is attempted. ``client.receive(on_event=...)`` is simulated by
having the patched client invoke the supplied callback against fake
``PartitionContext`` and event objects.
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from pipeline import consumer as consumer_module
from pipeline import metrics


class FakePartitionContext:
    def __init__(self, partition_id: str = "0") -> None:
        self.partition_id = partition_id
        self.update_checkpoint = MagicMock()


def _make_consumer(client: MagicMock) -> consumer_module.EventHubConsumer:
    """Construct an EventHubConsumer with the SDK boundary fully mocked."""
    with patch.object(consumer_module, "EventHubConsumerClient", return_value=client) as client_cls, \
         patch.object(consumer_module, "BlobCheckpointStore") as store_cls, \
         patch.object(consumer_module, "DefaultAzureCredential") as cred_cls:
        cred_cls.return_value = MagicMock(name="credential")
        c = consumer_module.EventHubConsumer(
            eventhub_namespace="ns.servicebus.windows.net",
            eventhub_name="source-a-events",
            consumer_group="$Default",
            checkpoint_store_url="https://acct.blob.core.windows.net",
            checkpoint_container="checkpoints",
            source_name="source-a",
        )
        c._test_client_cls = client_cls
        c._test_store_cls = store_cls
    return c


def _drive_one_event(client: MagicMock, event: object, partition_context: FakePartitionContext) -> None:
    """Make ``client.receive`` invoke its on_event callback once."""
    def fake_receive(*, on_event, **kwargs):
        on_event(partition_context, event)

    client.receive.side_effect = fake_receive


def _events_received(source: str) -> float:
    return metrics.events_received_total.labels(source=source)._value.get()


def test_constructor_wires_credential_and_sdk_objects():
    client = MagicMock(name="client")
    c = _make_consumer(client)
    c._test_store_cls.assert_called_once_with(
        blob_account_url="https://acct.blob.core.windows.net",
        container_name="checkpoints",
        credential=c._credential,
    )
    c._test_client_cls.assert_called_once()
    kwargs = c._test_client_cls.call_args.kwargs
    assert kwargs["fully_qualified_namespace"] == "ns.servicebus.windows.net"
    assert kwargs["eventhub_name"] == "source-a-events"
    assert kwargs["consumer_group"] == "$Default"
    assert kwargs["credential"] is c._credential
    assert kwargs["checkpoint_store"] is c._test_store_cls.return_value


def test_callback_success_triggers_checkpoint():
    client = MagicMock(name="client")
    c = _make_consumer(client)
    pc = FakePartitionContext()
    event = MagicMock(name="event")
    _drive_one_event(client, event, pc)

    callback = MagicMock(name="callback")
    shutdown = threading.Event()
    shutdown.set()  # let watcher exit immediately after receive returns
    c.run(callback, shutdown)

    callback.assert_called_once_with(event)
    pc.update_checkpoint.assert_called_once_with(event)


def test_callback_failure_skips_checkpoint():
    client = MagicMock(name="client")
    c = _make_consumer(client)
    pc = FakePartitionContext()
    event = MagicMock(name="event")
    _drive_one_event(client, event, pc)

    def boom(_event):
        raise RuntimeError("downstream blew up")

    shutdown = threading.Event()
    shutdown.set()
    c.run(boom, shutdown)

    pc.update_checkpoint.assert_not_called()


def test_each_event_increments_events_received_total():
    client = MagicMock(name="client")
    c = _make_consumer(client)
    pc = FakePartitionContext()

    before = _events_received("source-a")

    def fake_receive(*, on_event, **kwargs):
        on_event(pc, MagicMock())
        on_event(pc, MagicMock())
        on_event(pc, MagicMock())

    client.receive.side_effect = fake_receive
    shutdown = threading.Event()
    shutdown.set()
    c.run(MagicMock(), shutdown)

    after = _events_received("source-a")
    assert after - before == 3


def test_none_event_is_ignored_no_metric_no_checkpoint():
    """The SDK can deliver a ``None`` event when ``max_wait_time`` elapses
    with no message — should not count as received and should not checkpoint.
    """
    client = MagicMock(name="client")
    c = _make_consumer(client)
    pc = FakePartitionContext()

    before = _events_received("source-a")

    def fake_receive(*, on_event, **kwargs):
        on_event(pc, None)

    client.receive.side_effect = fake_receive
    callback = MagicMock()
    shutdown = threading.Event()
    shutdown.set()
    c.run(callback, shutdown)

    assert _events_received("source-a") == before
    callback.assert_not_called()
    pc.update_checkpoint.assert_not_called()


def test_shutdown_flag_closes_client_and_unblocks_run():
    """Setting the shutdown flag mid-receive must call client.close()."""
    client = MagicMock(name="client")
    c = _make_consumer(client)

    receive_started = threading.Event()
    receive_can_return = threading.Event()

    def blocking_receive(*, on_event, **kwargs):
        receive_started.set()
        receive_can_return.wait(timeout=5)

    def closing(*args, **kwargs):
        receive_can_return.set()

    client.receive.side_effect = blocking_receive
    client.close.side_effect = closing

    shutdown = threading.Event()
    runner = threading.Thread(target=c.run, args=(MagicMock(), shutdown))
    runner.start()
    assert receive_started.wait(timeout=5), "receive() did not start"

    shutdown.set()
    runner.join(timeout=5)
    assert not runner.is_alive(), "run() did not return after shutdown"
    client.close.assert_called()


def test_close_method_proxies_to_client():
    client = MagicMock(name="client")
    c = _make_consumer(client)
    c.close()
    client.close.assert_called_once()
