"""PropGateway source modules — contract & loader.

Each source the pipeline supports is a single Python module under this
package (e.g. ``pipeline.sources.source_a``). Adding a new source means
creating one file ``pipeline/sources/<name>.py`` that exports the
attributes below — no registration step, no config file to wire up.

Required exports
----------------

- ``SOURCE_NAME: str`` — identifier matching the worker's ``--source`` CLI
  argument and the value placed in ``envelope.source.system``.
- ``EVENT_HUB_NAMESPACE: str`` — fully qualified Event Hubs namespace
  (e.g. ``"prop-eventhub-ns.servicebus.windows.net"``).
- ``EVENT_HUB_NAME: str`` — the Event Hub the worker consumes from.
- ``KAFKA_OUTPUT_TOPIC: str`` — the Kafka topic enveloped events are
  published to (e.g. ``"propgateway.source-a"``).
- ``extract(raw_event: dict) -> tuple[dict, str]`` — pure function that
  takes the parsed event body and returns ``(metadata_dict, event_type)``.
  The ``metadata_dict`` becomes ``envelope.metadata``; ``event_type``
  becomes ``envelope.event.type``.

The four constants must be ``str``; ``extract`` must be callable. The
loader below enforces this and raises a ``TypeError`` naming the
offending attribute when the contract is violated.
"""

from __future__ import annotations

import importlib
from types import ModuleType

_REQUIRED_STR_ATTRS = (
    "SOURCE_NAME",
    "EVENT_HUB_NAMESPACE",
    "EVENT_HUB_NAME",
    "KAFKA_OUTPUT_TOPIC",
)


def load_source(name: str) -> ModuleType:
    """Import ``pipeline.sources.<name>`` and verify it satisfies the contract.

    Returns the imported module on success.

    Raises:
        ModuleNotFoundError: if no module ``pipeline.sources.<name>`` exists.
        TypeError: if the module exists but is missing a required attribute,
            a string attribute has the wrong type, or ``extract`` is missing
            or not callable. The message names the offending attribute.
    """
    full_name = f"pipeline.sources.{name}"
    module = importlib.import_module(full_name)

    for attr in _REQUIRED_STR_ATTRS:
        if not hasattr(module, attr):
            raise TypeError(
                f"source module '{full_name}' is missing required attribute {attr!r}"
            )
        value = getattr(module, attr)
        if not isinstance(value, str):
            raise TypeError(
                f"source module '{full_name}' attribute {attr!r} must be str, "
                f"got {type(value).__name__}"
            )

    if not hasattr(module, "extract"):
        raise TypeError(
            f"source module '{full_name}' is missing required attribute 'extract'"
        )
    if not callable(module.extract):
        raise TypeError(
            f"source module '{full_name}' attribute 'extract' must be callable, "
            f"got {type(module.extract).__name__}"
        )

    return module
