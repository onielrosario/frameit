"""
PROVISIONAL scoring — step 12's stand-in until the scoring engine at step 14.

Pure, synchronous, I/O-free (services/api/docs/CONTEXT.md). It takes signals that
have ALREADY survived span recovery and returns a result. It never sees a signal
that failed validation, so "re-score on surviving evidence only"
(architecture.md §4) holds by construction.

Every rule below is a literal reading of methodology.md §2, §3, §5, §7. None is
calibrated — there is no baseline yet (step 13) — and every threshold is the most
conservative reading available, because the correctness hierarchy puts "correctly
abstain" above "correct direction" (methodology §11). Expect step 14 to replace
this module rather than tune it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.models.analysis import ClassificationLabel
from app.models.taxonomy import CATEGORY_FAMILY

SCORING_VERSION = "0-provisional"

# methodology §5 / Q3's current default: below this, confidence caps at Medium
# and the evidence bar rises. Not a hard reject.
SHORT_INPUT_WORDS = 40

_STRENGTH_RANK = {"weak": 0, "moderate": 1, "strong": 2}

Side = Literal["left", "right"]
Band = Literal["slightly", "plain", "strongly"]

# Every label the scorer can emit, spelled out. A typo here is a type error, not
# a string that reaches a client and fails response validation at runtime.
_LABELS: dict[tuple[Band, Side], ClassificationLabel] = {
    ("slightly", "left"): "slightly_left",
    ("plain", "left"): "left",
    ("strongly", "left"): "strongly_left",
    ("slightly", "right"): "slightly_right",
    ("plain", "right"): "right",
    ("strongly", "right"): "strongly_right",
}

Status = Literal["classified", "unclear", "non_political"]
UnclearReason = Literal[
    "no_signals",
    "conflicting_directions",
    "interpretation_risk",
    "insufficient_neutral",
    "short_input_weak_only",
    "political_but_marked_non_political",
]


@dataclass(frozen=True)
class ScoredSignal:
    category: str
    direction: Literal["left", "right", "neutral"]
    strength: Literal["strong", "moderate", "weak"]


@dataclass(frozen=True)
class Score:
    status: Status
    label: ClassificationLabel | None
    confidence: Literal["high", "medium", "low"]
    evidence_strength: Literal["strong", "moderate", "weak"]
    unclear_reason: UnclearReason | None = None
    direction: Literal["left", "right", "center"] | None = None
    independent_categories: int = 0


def _max_strength(signals: list[ScoredSignal]) -> Literal["strong", "moderate", "weak"]:
    if not signals:
        return "weak"
    return max((s.strength for s in signals), key=_STRENGTH_RANK.__getitem__)


def score(
    signals: list[ScoredSignal],
    *,
    is_political: bool,
    interpretation_risk: str,
    word_count: int,
) -> Score:
    short = word_count < SHORT_INPUT_WORDS
    strength = _max_strength(signals)
    directional = [s for s in signals if s.direction != "neutral"]

    def unclear(reason: UnclearReason) -> Score:
        return Score("unclear", None, "low", strength, unclear_reason=reason)

    if not is_political:
        # A model that says "not political" and then reports surviving
        # directional evidence has contradicted itself. Abstain rather than pick
        # the half we like (Rule 12).
        if directional:
            return unclear("political_but_marked_non_political")
        return Score("non_political", None, "high" if not signals else "medium", "weak")

    # Sarcasm, satire, fragments, and text addressing the analyzer make any
    # directional read unreliable (methodology §10, threat-model §1).
    if interpretation_risk != "none":
        return unclear("interpretation_risk")

    if not signals:
        return unclear("no_signals")

    directions = {s.direction for s in directional}
    if len(directions) > 1:
        # There is no "Mixed" state and no averaging into a fake Center (§2).
        return unclear("conflicting_directions")

    if not directional:
        # Center needs ENOUGH evidence that does not favor a direction (§2) —
        # at least two independent neutral observations. One is a shrug.
        categories = {s.category for s in signals}
        if len(categories) < 2:
            return unclear("insufficient_neutral")
        return Score(
            "classified",
            "center",
            _confidence(signals, short),
            strength,
            direction="center",
            independent_categories=len(categories),
        )

    side: Side = "left" if "left" in directions else "right"
    # Independence (§3): count distinct categories, never raw findings. Three
    # loaded-language findings are one signal wearing three hats.
    categories = {s.category for s in directional}
    substantive = {s.category for s in directional if s.strength != "weak"}
    strong_families = {CATEGORY_FAMILY[s.category] for s in directional if s.strength == "strong"}
    strong_signals = sum(1 for s in directional if s.strength == "strong")

    if short and not substantive:
        # The evidence bar rises for short input (§5): weak inference alone does
        # not classify eight words.
        return unclear("short_input_weak_only")

    if strong_signals >= 2 and len(strong_families) >= 2:
        band: Band = "strongly"
    elif len(substantive) >= 2:
        # "Multiple consistent signals" — and a band above Slightly may not rest
        # primarily on weak ones (§6), so only moderate+ categories count.
        band = "plain"
    else:
        band = "slightly"

    return Score(
        "classified",
        _LABELS[band, side],
        _confidence(directional, short),
        strength,
        direction=side,
        independent_categories=len(categories),
    )


def _confidence(signals: list[ScoredSignal], short: bool) -> Literal["high", "medium", "low"]:
    """
    methodology §7: a deterministic function of independent categories, maximum
    strength, directional consistency (already guaranteed by the caller), and
    input length (short caps at Medium).
    """
    categories = {s.category for s in signals}
    strength = _max_strength(signals)
    level: Literal["high", "medium", "low"]
    if len(categories) >= 3 and strength == "strong":
        level = "high"
    elif len(categories) >= 2 or strength == "strong":
        level = "medium"
    else:
        level = "low"
    if short and level == "high":
        level = "medium"
    return level
