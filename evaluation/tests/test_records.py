from __future__ import annotations

import pytest
from conftest import make_record
from pydantic import ValidationError


def test_classified_record_requires_a_label() -> None:
    with pytest.raises(ValidationError):
        make_record(expected_status="classified", expected_label=None)


def test_unclear_record_may_not_carry_a_label() -> None:
    with pytest.raises(ValidationError):
        make_record(expected_status="unclear", expected_label="left", expected_direction="left")


def test_direction_must_agree_with_label() -> None:
    """A record whose own fields contradict each other would score Frame against nonsense."""
    with pytest.raises(ValidationError):
        make_record(expected_label="slightly_left", expected_direction="right")


def test_acceptable_labels_must_include_the_expected_label() -> None:
    with pytest.raises(ValidationError):
        make_record(acceptable_labels=["center"])


def test_unknown_field_is_rejected() -> None:
    """A typo'd field name would silently do nothing."""
    with pytest.raises(ValidationError):
        make_record(expcted_confidence="high")
