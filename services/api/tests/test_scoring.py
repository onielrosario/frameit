"""
Provisional scoring (step 12) — table-driven over signal sets.

These pin the methodology's rules, not calibrated thresholds: independence,
no-Mixed, Center vs Unclear, the short-input cap, abstention on risk.
"""

from __future__ import annotations

import pytest

from app.scoring.provisional import ScoredSignal as S
from app.scoring.provisional import score

LONG = 120
SHORT = 12


def run(signals, *, political=True, risk="none", words=LONG):
    return score(signals, is_political=political, interpretation_risk=risk, word_count=words)


def test_three_loaded_language_findings_do_not_reach_a_strong_label() -> None:
    """methodology §3: one signal wearing three hats."""
    result = run([S("loaded_language", "left", "strong")] * 3)
    assert result.label == "slightly_left"


def test_strong_label_needs_strong_signals_in_independent_families() -> None:
    same_family = run(
        [S("loaded_language", "right", "strong"), S("fear_framing", "right", "strong")]
    )
    assert same_family.label == "right"
    independent = run(
        [S("policy_framing", "right", "strong"), S("fear_framing", "right", "strong")]
    )
    assert independent.label == "strongly_right"


def test_weak_signals_cannot_lift_a_band_above_slightly() -> None:
    result = run(
        [
            S("policy_framing", "left", "weak"),
            S("loaded_language", "left", "weak"),
            S("viewpoint_treatment", "left", "weak"),
        ]
    )
    assert result.label == "slightly_left"


def test_multiple_consistent_moderate_signals_reach_the_middle_band() -> None:
    assert (
        run(
            [S("policy_framing", "left", "moderate"), S("loaded_language", "left", "moderate")]
        ).label
        == "left"
    )


def test_conflicting_directions_are_unclear_never_averaged_to_center() -> None:
    result = run([S("policy_framing", "left", "strong"), S("loaded_language", "right", "strong")])
    assert result.status == "unclear" and result.unclear_reason == "conflicting_directions"


def test_center_needs_two_independent_neutral_observations() -> None:
    assert run([S("viewpoint_treatment", "neutral", "moderate")]).status == "unclear"
    center = run(
        [
            S("viewpoint_treatment", "neutral", "moderate"),
            S("argument_emphasis", "neutral", "moderate"),
        ]
    )
    assert center.status == "classified" and center.label == "center"


def test_neutral_signals_do_not_block_a_directional_read() -> None:
    result = run(
        [S("policy_framing", "left", "moderate"), S("viewpoint_treatment", "neutral", "moderate")]
    )
    assert result.label == "slightly_left"


def test_no_signals_on_political_content_is_unclear() -> None:
    assert run([]).status == "unclear"


@pytest.mark.parametrize("risk", ["sarcasm", "satire", "fragmentary", "addresses_analyzer"])
def test_interpretation_risk_abstains_even_with_strong_evidence(risk: str) -> None:
    signals = [
        S("policy_framing", "left", "strong"),
        S("fear_framing", "left", "strong"),
        S("viewpoint_treatment", "left", "strong"),
    ]
    assert run(signals, risk=risk).status == "unclear"


def test_short_input_caps_confidence_at_medium() -> None:
    signals = [
        S("policy_framing", "left", "strong"),
        S("fear_framing", "left", "strong"),
        S("viewpoint_treatment", "left", "strong"),
    ]
    assert run(signals).confidence == "high"
    assert run(signals, words=SHORT).confidence == "medium"


def test_short_input_with_only_weak_signals_is_unclear() -> None:
    assert run([S("loaded_language", "left", "weak")], words=SHORT).status == "unclear"
    assert run([S("loaded_language", "left", "weak")]).status == "classified"


def test_non_political_with_no_signals() -> None:
    assert run([], political=False).status == "non_political"


def test_self_contradicting_non_political_abstains() -> None:
    result = run([S("policy_framing", "left", "strong")], political=False)
    assert result.status == "unclear"
