from __future__ import annotations

from conftest import make_outcome, make_record

from frame_eval import metrics
from frame_eval.metrics import Prediction


def predict(**overrides) -> Prediction:
    base = {"status": "classified", "label": "slightly_left", "confidence": "medium"}
    base.update(overrides)
    return Prediction(**base)  # type: ignore[arg-type]


# --- §5.1 grounding: the hard gate ---------------------------------------


def test_grounding_counts_every_displayed_excerpt() -> None:
    outcome = make_outcome(
        make_record(),
        predict(evidence=(("policy_framing", "a"), ("policy_framing", "b"))),
        grounded=[True, False],
    )
    result = metrics.grounding([outcome])
    assert (result.grounded, result.total) == (1, 2)
    assert result.rate == 0.5
    assert result.ungrounded_examples == (("ev_0001", "b"),)


def test_grounding_rate_is_none_rather_than_one_when_nothing_was_displayed() -> None:
    """
    Zero excerpts is not 100% grounding. Reporting 1.0 there would let a system
    that displays nothing claim a perfect score on the hard gate.
    """
    result = metrics.grounding([make_outcome(make_record(), predict())])
    assert result.total == 0
    assert result.rate is None


# --- §5.2 abstention ------------------------------------------------------


def test_abstention_separates_over_from_under() -> None:
    outcomes = [
        make_outcome(
            make_record(
                id="a",
                expected_status="unclear",
                expected_label=None,
                expected_direction="none",
                acceptable_labels=[],
            ),
            predict(status="unclear", label=None),
        ),
        make_outcome(make_record(id="b"), predict(status="unclear", label=None)),
        make_outcome(
            make_record(
                id="c",
                expected_status="unclear",
                expected_label=None,
                expected_direction="none",
                acceptable_labels=[],
            ),
            predict(status="classified"),
        ),
        make_outcome(make_record(id="d"), predict(status="classified")),
    ]
    result = metrics.abstention(outcomes)
    assert (result.correct, result.over, result.under, result.not_applicable) == (1, 1, 1, 1)


# --- §5.3 directional agreement ------------------------------------------


def test_band_adjacent_gets_partial_credit() -> None:
    outcome = make_outcome(make_record(), predict(label="center"))
    result = metrics.directional_agreement([outcome])
    assert (result.exact, result.band_adjacent, result.reversal) == (0, 1, 0)


def test_direction_reversal_is_counted_separately_from_being_one_band_off() -> None:
    """
    A reversal is qualitatively different from a near miss and must never be
    averaged into the same number (§5.3).
    """
    outcome = make_outcome(make_record(), predict(label="slightly_right"))
    result = metrics.directional_agreement([outcome])
    assert (result.band_adjacent, result.reversal) == (0, 1)
    assert result.agreement_rate == 0.0


def test_unknown_label_from_a_newer_api_is_skipped_not_counted_as_wrong() -> None:
    outcome = make_outcome(make_record(), predict(label="partially_framed"))
    assert metrics.directional_agreement([outcome]).total == 0


# --- §5.4 propaganda ------------------------------------------------------


def test_propaganda_precision_and_recall_are_per_technique() -> None:
    outcomes = [
        make_outcome(
            make_record(id="a", expected_propaganda=["fear_appeal"]),
            predict(propaganda=("fear_appeal",)),
        ),
        make_outcome(
            make_record(id="b", expected_propaganda=[]), predict(propaganda=("fear_appeal",))
        ),
        make_outcome(
            make_record(id="c", expected_propaganda=["scapegoating"]), predict(propaganda=())
        ),
    ]
    scores = metrics.propaganda_agreement(outcomes)
    assert scores["fear_appeal"].precision == 0.5
    assert scores["fear_appeal"].recall == 1.0
    assert scores["scapegoating"].recall == 0.0


# --- §4 / §5.5 mirror symmetry -------------------------------------------


def _mirror_pair(left_prediction: Prediction, right_prediction: Prediction):
    left = make_record(id="ev_l", mirror_of="ev_r")
    right = make_record(
        id="ev_r",
        mirror_of="ev_l",
        expected_label="slightly_right",
        expected_direction="right",
        acceptable_labels=["center", "slightly_right"],
    )
    return [make_outcome(left, left_prediction), make_outcome(right, right_prediction)]


def test_mirrored_labels_of_equal_magnitude_pass() -> None:
    results = metrics.mirror_symmetry(
        _mirror_pair(predict(label="slightly_left"), predict(label="slightly_right"))
    )
    assert len(results) == 1
    assert results[0].passed


def test_asymmetric_magnitude_fails_even_when_direction_is_right() -> None:
    """The failure this instrument exists to catch: same structure, stronger read on one side."""
    results = metrics.mirror_symmetry(
        _mirror_pair(predict(label="slightly_left"), predict(label="strongly_right"))
    )
    assert not results[0].passed
    assert not results[0].label_symmetric


def test_asymmetric_propaganda_flagging_fails() -> None:
    results = metrics.mirror_symmetry(
        _mirror_pair(
            predict(label="slightly_left", propaganda=("fear_appeal",)),
            predict(label="slightly_right"),
        )
    )
    assert not results[0].propaganda_matches


def test_confidence_one_band_apart_is_tolerated_two_is_not() -> None:
    close = metrics.mirror_symmetry(
        _mirror_pair(
            predict(label="slightly_left", confidence="high"),
            predict(label="slightly_right", confidence="medium"),
        )
    )
    far = metrics.mirror_symmetry(
        _mirror_pair(
            predict(label="slightly_left", confidence="high"),
            predict(label="slightly_right", confidence="low"),
        )
    )
    assert close[0].confidence_within_one_band
    assert not far[0].confidence_within_one_band


def test_each_mirror_pair_is_reported_once() -> None:
    results = metrics.mirror_symmetry(
        _mirror_pair(predict(label="slightly_left"), predict(label="slightly_right"))
    )
    assert len(results) == 1
