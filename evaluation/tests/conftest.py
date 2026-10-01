"""
Fixtures for harness tests.

These records are FIXTURES, not evaluation data. They exist to exercise the
metrics and never appear in evaluation/dataset/ — a fixture written by whoever
wrote the metric is worthless as ground truth and would corrupt the dataset if
it leaked in.
"""

from __future__ import annotations

import pytest

from frame_eval.metrics import Outcome, Prediction
from frame_eval.records import Record


def make_record(**overrides) -> Record:
    base = {
        "id": "ev_0001",
        "input": "Working families must be protected from rising costs this winter.",
        "source_type": "synthetic",
        "expected_status": "classified",
        "expected_label": "slightly_left",
        "expected_direction": "left",
        "acceptable_labels": ["center", "slightly_left"],
        "expected_evidence": [],
        "expected_confidence": "medium",
        "expected_propaganda": [],
        "rationale": "fixture",
        "mirror_of": None,
        "split": "dev",
        "review_state": "reviewed",
        "label_provenance": "human_blind",
        "reviewers": ["fixture"],
        "disagreement_note": None,
    }
    base.update(overrides)
    return Record.model_validate(base)


def make_outcome(
    record: Record, prediction: Prediction, grounded: list[bool] | None = None
) -> Outcome:
    return Outcome(
        record=record,
        prediction=prediction,
        grounded=grounded if grounded is not None else [True] * len(prediction.evidence),
    )


@pytest.fixture
def record_factory():
    return make_record


@pytest.fixture
def outcome_factory():
    return make_outcome
