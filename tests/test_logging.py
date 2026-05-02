"""Tests for shared.logging."""

import json
import logging

import pytest

from shared.logging import log_context, setup_logging


@pytest.fixture(autouse=True)
def _clean_root_logger_after_test():
    """Strip handlers between tests so output from one test cannot reach another."""
    yield
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)


def _read_one_line(capsys) -> dict:
    captured = capsys.readouterr()
    lines = [ln for ln in captured.out.splitlines() if ln.strip()]
    assert len(lines) == 1, f"expected one log line, got {lines!r}"
    return json.loads(lines[0])


def test_emitted_line_has_required_schema(capsys):
    setup_logging("source-a")
    logging.getLogger("propgateway.test").info("hello")

    record = _read_one_line(capsys)
    assert set(record.keys()) >= {
        "timestamp",
        "level",
        "source",
        "correlation_id",
        "envelope_id",
        "message",
    }
    assert record["level"] == "INFO"
    assert record["source"] == "source-a"
    assert record["message"] == "hello"
    assert "T" in record["timestamp"]
    assert record["timestamp"].endswith("+00:00")


def test_correlation_and_envelope_id_default_to_null(capsys):
    setup_logging("source-a")
    logging.getLogger("propgateway.test").info("hello")

    record = _read_one_line(capsys)
    assert record["correlation_id"] is None
    assert record["envelope_id"] is None


def test_log_context_propagates_ids(capsys):
    setup_logging("source-a")
    with log_context(correlation_id="corr-1", envelope_id="env-1"):
        logging.getLogger("propgateway.test").info("processing")

    record = _read_one_line(capsys)
    assert record["correlation_id"] == "corr-1"
    assert record["envelope_id"] == "env-1"


def test_log_context_clears_after_block(capsys):
    setup_logging("source-a")
    log = logging.getLogger("propgateway.test")
    with log_context(correlation_id="corr-1", envelope_id="env-1"):
        pass
    log.info("after-block")

    record = _read_one_line(capsys)
    assert record["correlation_id"] is None
    assert record["envelope_id"] is None


def test_nested_log_context_restores_outer_on_exit(capsys):
    setup_logging("source-a")
    log = logging.getLogger("propgateway.test")
    with log_context(correlation_id="outer", envelope_id="env-outer"):
        with log_context(correlation_id="inner", envelope_id="env-inner"):
            log.info("inner-line")
        log.info("outer-line")

    captured = capsys.readouterr()
    lines = [json.loads(ln) for ln in captured.out.splitlines() if ln.strip()]
    assert len(lines) == 2
    assert lines[0]["correlation_id"] == "inner"
    assert lines[0]["envelope_id"] == "env-inner"
    assert lines[1]["correlation_id"] == "outer"
    assert lines[1]["envelope_id"] == "env-outer"


def test_partial_log_context_only_sets_provided_ids(capsys):
    setup_logging("source-a")
    with log_context(correlation_id="corr-only"):
        logging.getLogger("propgateway.test").info("partial")

    record = _read_one_line(capsys)
    assert record["correlation_id"] == "corr-only"
    assert record["envelope_id"] is None


def test_extra_fields_pass_through(capsys):
    setup_logging("source-a")
    logging.getLogger("propgateway.test").info(
        "event", extra={"policy_id": "P-123", "retry_count": 2}
    )

    record = _read_one_line(capsys)
    assert record["policy_id"] == "P-123"
    assert record["retry_count"] == 2


def test_setup_logging_replaces_handlers_on_repeat_call(capsys):
    setup_logging("source-a")
    setup_logging("source-b")
    logging.getLogger("propgateway.test").info("hello")

    record = _read_one_line(capsys)
    assert record["source"] == "source-b"


def test_level_filter_applied(capsys):
    setup_logging("source-a", level="WARNING")
    log = logging.getLogger("propgateway.test")
    log.info("filtered-out")
    log.warning("kept")

    record = _read_one_line(capsys)
    assert record["level"] == "WARNING"
    assert record["message"] == "kept"


def test_non_json_serialisable_extra_falls_back_to_str(capsys):
    setup_logging("source-a")

    class Weird:
        def __str__(self) -> str:
            return "weird-repr"

    logging.getLogger("propgateway.test").info("event", extra={"obj": Weird()})

    record = _read_one_line(capsys)
    assert record["obj"] == "weird-repr"
