"""
Evidence validator tests.

The standard in services/api/docs/CONTEXT.md is mutation-style: paraphrase,
curly quotes, collapsed whitespace, injected ellipses, outright fabrication —
each with an asserted outcome.

The threshold itself is NOT asserted as a constant. `test_threshold_separates…`
measures every case and asserts the must-recover and must-reject groups do not
overlap, with the threshold in the gap. A number chosen to make today's tests
pass is a number picked by feel; a measured gap is a fact that survives new cases
being added.
"""

from __future__ import annotations

import logging

import pytest

from app.evidence.normalize import normalize
from app.evidence.recover import FUZZY_THRESHOLD, Recovered, Rejected, recover

SOURCE = (
    "The governor said working families must be protected from rising energy costs "
    'this winter. Critics refused to consider the proposal, calling it "reckless '
    'spending" that the state - by their own accounting - cannot afford.'
)

CONTENT = normalize(SOURCE)

# (name, model excerpt). Differences that normalization exists to erase must come
# back through the EXACT path — if one of these ever recovers as "fuzzy", the
# normalizer stopped folding something and leniency is covering for it.
FOLD_CASES = [
    ("verbatim", "working families must be protected from rising energy costs"),
    ("curly quotes for straight", "calling it “reckless spending” that the state"),
    ("em dash for hyphen", "the state — by their own accounting — cannot afford"),
    ("nbsp for space", "Critics refused to consider"),
    ("collapsed whitespace", "working   families\n\nmust be protected"),
    ("case change", "Working Families Must Be Protected"),
]

# Genuine drift in the model's transcription. Must recover, via fuzzy.
DRIFT_CASES = [
    ("one-character typo", "working familes must be protected from rising energy costs"),
    ("punctuation swapped at the end", "Critics refused to consider the proposal."),
    (
        "small elision marked with an ellipsis",
        "working families must be protected … from rising energy costs",
    ),
]

# Must reject. Displaying any of these would put text on screen that is not in
# the submission.
REJECT_CASES = [
    ("distant paraphrase", "households need shielding from higher power bills"),
    ("close paraphrase", "the governor said households must be shielded from rising energy prices"),
    ("outright fabrication", "the governor promised a complete refund to every household"),
    (
        "fabricated clause appended",
        "Critics refused to consider the proposal and walked out in protest",
    ),
    (
        "elision so large the span is not what was quoted",
        "working families must be protected … cannot afford",
    ),
]


@pytest.mark.parametrize(("name", "excerpt"), FOLD_CASES, ids=[c[0] for c in FOLD_CASES])
def test_normalization_differences_recover_exactly(name: str, excerpt: str) -> None:
    outcome = recover(CONTENT, excerpt)
    assert isinstance(outcome, Recovered)
    assert outcome.method in {"exact", "exact_ambiguous"}, (
        f"{name} recovered as {outcome.method}: normalization should have erased this "
        "difference before comparison, not fuzzy leniency"
    )


@pytest.mark.parametrize(("name", "excerpt"), DRIFT_CASES, ids=[c[0] for c in DRIFT_CASES])
def test_transcription_drift_recovers(name: str, excerpt: str) -> None:
    outcome = recover(CONTENT, excerpt)
    assert isinstance(outcome, Recovered), f"{name} was rejected"
    assert outcome.method == "fuzzy"


@pytest.mark.parametrize(("name", "excerpt"), REJECT_CASES, ids=[c[0] for c in REJECT_CASES])
def test_unsupported_excerpts_are_rejected(name: str, excerpt: str) -> None:
    assert isinstance(recover(CONTENT, excerpt), Rejected), f"{name} was accepted"


def test_displayed_excerpt_is_the_source_substring_not_the_model_string() -> None:
    """
    The rule the whole module exists for: the model's string is a query, not
    content (architecture.md §4).
    """
    typo = "working familes must be protected from rising energy costs"
    outcome = recover(CONTENT, typo)
    assert isinstance(outcome, Recovered)

    assert outcome.excerpt == CONTENT.text[outcome.start : outcome.end]
    assert outcome.excerpt != typo
    assert "familes" not in outcome.excerpt, "the model's misspelling must not reach the screen"
    assert "families" in outcome.excerpt


def test_recovered_span_maps_back_to_the_original_submission() -> None:
    """Spans are into normalized content, and must survive the trip back (§5)."""
    outcome = recover(CONTENT, "Critics refused to consider")
    assert isinstance(outcome, Recovered)
    start, end = CONTENT.to_original_span(outcome.start, outcome.end)
    assert SOURCE[start:end] == "Critics refused to consider"


def test_repeated_phrase_is_flagged_ambiguous_not_silently_resolved() -> None:
    content = normalize("the plan is bold. the plan is costly. the plan is here.")
    outcome = recover(content, "the plan")
    assert isinstance(outcome, Recovered)
    assert outcome.method == "exact_ambiguous"
    assert outcome.start == 0, "first hit wins"


@pytest.mark.parametrize("excerpt", ["", "   ", "\n\t"])
def test_empty_excerpts_are_rejected(excerpt: str) -> None:
    outcome = recover(CONTENT, excerpt)
    assert isinstance(outcome, Rejected)
    assert outcome.reason == "empty"


def test_rejection_is_logged_with_the_model_excerpt(caplog: pytest.LogCaptureFixture) -> None:
    """
    A rising rejection rate is the best early warning of a bad prompt or a model
    change, and it is invisible without the excerpt (architecture.md §4).
    """
    with caplog.at_level(logging.INFO, logger="frame.evidence"):
        recover(CONTENT, "the governor promised a complete refund")

    record = next(r for r in caplog.records if r.message == "evidence_rejected")
    assert record.model_excerpt == "the governor promised a complete refund"
    assert record.reason == "below_threshold"
    assert isinstance(record.best_similarity, float)


def test_threshold_separates_the_two_groups_with_margin() -> None:
    """
    The threshold is derived, not chosen.

    Every must-recover case scores above every must-reject case, and
    FUZZY_THRESHOLD sits in the gap between them. If a future case narrows that
    gap to nothing, no threshold works and this fails loudly rather than letting
    one group quietly bleed into the other.
    """

    def score(excerpt: str) -> float:
        outcome = recover(CONTENT, excerpt)
        return outcome.similarity if isinstance(outcome, Recovered) else outcome.best_similarity

    recover_scores = {name: score(text) for name, text in FOLD_CASES + DRIFT_CASES}
    reject_scores = {name: score(text) for name, text in REJECT_CASES}

    lowest_recover = min(recover_scores.values())
    highest_reject = max(reject_scores.values())

    assert highest_reject < lowest_recover, (
        "must-recover and must-reject overlap; no threshold can separate them.\n"
        f"  highest reject: {max(reject_scores, key=reject_scores.get)} = {highest_reject:.3f}\n"
        f"  lowest recover: {min(recover_scores, key=recover_scores.get)} = {lowest_recover:.3f}"
    )
    assert highest_reject < FUZZY_THRESHOLD <= lowest_recover, (
        f"FUZZY_THRESHOLD {FUZZY_THRESHOLD} is outside the measured gap "
        f"({highest_reject:.3f}, {lowest_recover:.3f}]"
    )
