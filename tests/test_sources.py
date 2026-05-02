"""Tests for pipeline.sources.load_source.

Fixture source modules are constructed in-memory as ``types.ModuleType``
instances and registered under ``pipeline.sources.<name>`` in
``sys.modules``. ``importlib.import_module`` returns cached entries from
``sys.modules`` without touching disk, so the loader exercises the same
code path it would for a real on-disk source. See ADR 0008.
"""

import sys
from types import ModuleType

import pytest

from pipeline.sources import load_source


VALID_ATTRS = {
    "SOURCE_NAME": "fake-source",
    "EVENT_HUB_NAMESPACE": "ns.servicebus.windows.net",
    "EVENT_HUB_NAME": "fake-events",
    "KAFKA_OUTPUT_TOPIC": "propgateway.fake",
    "extract": lambda raw_event: ({}, "status_update"),
}


@pytest.fixture
def register_source():
    """Yield a helper that registers fake source modules and cleans up."""
    registered: list[str] = []

    def _register(name: str, **attrs) -> ModuleType:
        full_name = f"pipeline.sources.{name}"
        module = ModuleType(full_name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[full_name] = module
        registered.append(full_name)
        return module

    yield _register

    for full_name in registered:
        sys.modules.pop(full_name, None)


def test_load_nonexistent_source_raises_with_name_in_message():
    with pytest.raises(ModuleNotFoundError) as excinfo:
        load_source("definitely_does_not_exist_xyz")
    assert "definitely_does_not_exist_xyz" in str(excinfo.value)


def test_load_valid_source_returns_module(register_source):
    register_source("valid_fake", **VALID_ATTRS)
    module = load_source("valid_fake")
    assert module.SOURCE_NAME == "fake-source"
    assert module.EVENT_HUB_NAMESPACE == "ns.servicebus.windows.net"
    assert module.EVENT_HUB_NAME == "fake-events"
    assert module.KAFKA_OUTPUT_TOPIC == "propgateway.fake"
    assert callable(module.extract)


def test_missing_string_attribute_names_the_attribute(register_source):
    attrs = dict(VALID_ATTRS)
    attrs.pop("EVENT_HUB_NAME")
    register_source("missing_event_hub_name", **attrs)
    with pytest.raises(TypeError) as excinfo:
        load_source("missing_event_hub_name")
    assert "EVENT_HUB_NAME" in str(excinfo.value)


def test_string_attribute_with_wrong_type_names_the_attribute(register_source):
    attrs = dict(VALID_ATTRS)
    attrs["KAFKA_OUTPUT_TOPIC"] = 42
    register_source("wrong_type_topic", **attrs)
    with pytest.raises(TypeError) as excinfo:
        load_source("wrong_type_topic")
    message = str(excinfo.value)
    assert "KAFKA_OUTPUT_TOPIC" in message
    assert "str" in message
    assert "int" in message


def test_missing_extract_names_the_attribute(register_source):
    attrs = dict(VALID_ATTRS)
    attrs.pop("extract")
    register_source("no_extract", **attrs)
    with pytest.raises(TypeError) as excinfo:
        load_source("no_extract")
    assert "extract" in str(excinfo.value)


def test_extract_not_callable_names_the_attribute(register_source):
    attrs = dict(VALID_ATTRS)
    attrs["extract"] = "not a function"
    register_source("bad_extract", **attrs)
    with pytest.raises(TypeError) as excinfo:
        load_source("bad_extract")
    message = str(excinfo.value)
    assert "extract" in message
    assert "callable" in message
