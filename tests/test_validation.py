"""Tests for pipeline.validation."""

from pipeline.validation import ValidationResult, validate


def test_pass_when_all_required_fields_present():
    result = validate({"type": "status_update", "data": {"x": 1}}, ["type", "data"])
    assert result == ValidationResult(True, None)
    assert result.ok is True
    assert result.reason is None


def test_fail_when_raw_event_not_a_dict():
    result = validate("not a dict", ["type"])
    assert result.ok is False
    assert result.reason is not None
    assert "dict" in result.reason


def test_fail_when_raw_event_is_none():
    result = validate(None, ["type"])
    assert result.ok is False
    assert result.reason is not None
    assert "dict" in result.reason


def test_fail_when_required_field_missing_names_the_field():
    result = validate({"type": "status_update"}, ["type", "data"])
    assert result.ok is False
    assert result.reason is not None
    assert "data" in result.reason


def test_pass_when_required_fields_empty():
    result = validate({}, [])
    assert result == ValidationResult(True, None)


def test_extra_fields_do_not_fail():
    result = validate({"type": "x", "extra": 1}, ["type"])
    assert result.ok is True


def test_required_field_present_with_falsy_value_passes():
    result = validate({"type": "x", "data": None}, ["type", "data"])
    assert result.ok is True
