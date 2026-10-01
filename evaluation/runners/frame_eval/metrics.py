"""
Metrics, per docs/evaluation.md §5. Pure functions over (record, prediction)
pairs — no I/O, no model, so the harness is testable without spending tokens.

Naming follows §7: this computes **agreement with our reviewers**, never
"accuracy". There is no external ground truth for how left-leaning a paragraph
is; there is only inter-reviewer agreement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from frame_eval.records import LABEL_ORDER, Record, direction_of


@dataclass(frozen=True)
class Prediction:
    """What Frame returned, reduced to what the metrics need."""

    status: str
    label: str | None
    confidence: str | None
    # (category, excerpt) for every excerpt that would be DISPLAYED.
    evidence: tuple[tuple[str, str], ...] = ()
    propaganda: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class Grounding:
    """§5.1 — the hard gate. Target 100%; a single failure is a release blocker."""

    grounded: int
    total: int
    ungrounded_examples: tuple[tuple[str, str], ...] = ()

    @property
    def rate(self) -> float | None:
        return None if self.total == 0 else self.grounded / self.total


@dataclass(frozen=True)
class Abstention:
    """§5.2 — reported in both directions, because they fail differently."""

    correct: int = 0
    over: int = 0
    under: int = 0
    # Reviewer classified, Frame classified. Not an abstention outcome.
    not_applicable: int = 0


@dataclass(frozen=True)
class DirectionalAgreement:
    """§5.3 — reversals are counted separately and prominently."""

    exact: int = 0
    band_adjacent: int = 0
    other_same_direction: int = 0
    reversal: int = 0
    total: int = 0

    @property
    def agreement_rate(self) -> float | None:
        """Exact plus band-adjacent, the credit-earning outcomes."""
        if self.total == 0:
            return None
        return (self.exact + self.band_adjacent) / self.total


@dataclass(frozen=True)
class TechniqueScore:
    true_positive: int = 0
    false_positive: int = 0
    false_negative: int = 0

    @property
    def precision(self) -> float | None:
        denominator = self.true_positive + self.false_positive
        return None if denominator == 0 else self.true_positive / denominator

    @property
    def recall(self) -> float | None:
        denominator = self.true_positive + self.false_negative
        return None if denominator == 0 else self.true_positive / denominator


@dataclass(frozen=True)
class MirrorResult:
    pair: tuple[str, str]
    label_symmetric: bool
    confidence_within_one_band: bool
    propaganda_matches: bool
    categories_match: bool

    @property
    def passed(self) -> bool:
        return (
            self.label_symmetric
            and self.confidence_within_one_band
            and self.propaganda_matches
            and self.categories_match
        )


@dataclass
class Outcome:
    record: Record
    prediction: Prediction
    # Per displayed excerpt: is it an exact substring of the normalized input?
    grounded: list[bool] = field(default_factory=list)


def grounding(outcomes: list[Outcome]) -> Grounding:
    grounded = 0
    total = 0
    failures: list[tuple[str, str]] = []
    for outcome in outcomes:
        for (_, excerpt), is_grounded in zip(
            outcome.prediction.evidence, outcome.grounded, strict=True
        ):
            total += 1
            if is_grounded:
                grounded += 1
            else:
                failures.append((outcome.record.id, excerpt))
    return Grounding(grounded=grounded, total=total, ungrounded_examples=tuple(failures))


def abstention(outcomes: list[Outcome]) -> Abstention:
    correct = over = under = not_applicable = 0
    for outcome in outcomes:
        reviewer_unclear = outcome.record.expected_status == "unclear"
        frame_unclear = outcome.prediction.status == "unclear"
        if reviewer_unclear and frame_unclear:
            correct += 1
        elif not reviewer_unclear and frame_unclear:
            # The product-killing direction: it is what makes people stop using it.
            over += 1
        elif reviewer_unclear and not frame_unclear:
            # The trust-killing direction. Worse, but it does not let
            # over-abstention hide behind "abstention is a success".
            under += 1
        else:
            not_applicable += 1
    return Abstention(correct=correct, over=over, under=under, not_applicable=not_applicable)


def directional_agreement(outcomes: list[Outcome]) -> DirectionalAgreement:
    exact = band_adjacent = other_same = reversal = total = 0
    for outcome in outcomes:
        expected = outcome.record.expected_label
        predicted = outcome.prediction.label
        if expected is None or predicted is None:
            continue
        if predicted not in LABEL_ORDER:
            continue
        total += 1

        if predicted == expected:
            exact += 1
            continue

        predicted_direction = direction_of(predicted)  # type: ignore[arg-type]
        expected_direction = direction_of(expected)
        if predicted_direction != expected_direction and "none" not in (
            predicted_direction,
            expected_direction,
        ):
            reversal += 1
            continue

        if predicted in outcome.record.acceptable_labels:
            band_adjacent += 1
            continue

        distance = abs(LABEL_ORDER.index(predicted) - LABEL_ORDER.index(expected))  # type: ignore[arg-type]
        if distance == 1:
            band_adjacent += 1
        else:
            other_same += 1

    return DirectionalAgreement(
        exact=exact,
        band_adjacent=band_adjacent,
        other_same_direction=other_same,
        reversal=reversal,
        total=total,
    )


def propaganda_agreement(outcomes: list[Outcome]) -> dict[str, TechniqueScore]:
    """
    §5.4 — per technique. Precision matters far more than recall: a false
    "fear appeal" on ordinary advocacy is a much worse error than a missed one.
    """
    scores: dict[str, TechniqueScore] = {}
    for outcome in outcomes:
        expected = set(outcome.record.expected_propaganda)
        predicted = set(outcome.prediction.propaganda)
        for technique in expected | predicted:
            current = scores.get(technique, TechniqueScore())
            scores[technique] = TechniqueScore(
                true_positive=current.true_positive
                + (technique in expected and technique in predicted),
                false_positive=current.false_positive
                + (technique in predicted and technique not in expected),
                false_negative=current.false_negative
                + (technique in expected and technique not in predicted),
            )
    return scores


_CONFIDENCE_ORDER = ("low", "medium", "high")


def compare_predictions(
    pair: tuple[str, str], first: Prediction, second: Prediction
) -> MirrorResult:
    """
    The mirror assertions from docs/evaluation.md §4, in one place.

    Public because the marketing renderer uses the same rule. A demo asserting
    symmetry by a different definition than the harness enforces would be a
    claim nothing in the repo checks.
    """
    return MirrorResult(
        pair=pair,
        label_symmetric=_labels_symmetric(first.label, second.label),
        confidence_within_one_band=_confidence_close(first.confidence, second.confidence),
        propaganda_matches=sorted(first.propaganda) == sorted(second.propaganda),
        categories_match=sorted(c for c, _ in first.evidence)
        == sorted(c for c, _ in second.evidence),
    )


def mirror_symmetry(outcomes: list[Outcome]) -> list[MirrorResult]:
    """
    §4 — the most important instrument in the evaluation doc.

    Frame's credibility dies the day someone shows that structurally identical
    left- and right-leaning passages get systematically different treatment.
    """
    by_id = {outcome.record.id: outcome for outcome in outcomes}
    results: list[MirrorResult] = []
    seen: set[frozenset[str]] = set()

    for outcome in outcomes:
        twin_id = outcome.record.mirror_of
        if not twin_id or twin_id not in by_id:
            continue
        key = frozenset({outcome.record.id, twin_id})
        if key in seen:
            continue
        seen.add(key)
        twin = by_id[twin_id]
        results.append(
            compare_predictions((outcome.record.id, twin_id), outcome.prediction, twin.prediction)
        )
    return results


def _labels_symmetric(first: str | None, second: str | None) -> bool:
    """Symmetric in MAGNITUDE: slightly_left <-> slightly_right, center <-> center."""
    if first is None or second is None:
        return first == second
    if first not in LABEL_ORDER or second not in LABEL_ORDER:
        return False
    middle = (len(LABEL_ORDER) - 1) / 2
    return abs(LABEL_ORDER.index(first) - middle) == abs(LABEL_ORDER.index(second) - middle) and (
        direction_of(first) != direction_of(second) or first == second == "center"  # type: ignore[arg-type]
    )


def _confidence_close(first: str | None, second: str | None) -> bool:
    if first is None or second is None:
        return first == second
    if first not in _CONFIDENCE_ORDER or second not in _CONFIDENCE_ORDER:
        return False
    return abs(_CONFIDENCE_ORDER.index(first) - _CONFIDENCE_ORDER.index(second)) <= 1
