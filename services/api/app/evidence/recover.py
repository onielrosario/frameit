"""
Span recovery — the evidence validator.

Not accept/reject (architecture.md §4). The model's excerpt is a **query**, not
content. What gets displayed is always `normalized[start:end]` — the source
substring — so a recovered item shows the reader what the page actually says,
even when the model's own string drifted.

Pure, synchronous, I/O-free apart from a log line on rejection.

Rejections are logged with the model's excerpt, because a rising rejection rate
is the single best early warning of a bad prompt or a model change. The excerpt
is a fragment and falls under the retention rules in threat-model.md §3.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from app.evidence.normalize import Normalized, normalize

logger = logging.getLogger("frame.evidence")

# PROVISIONAL. architecture.md §4 requires this to be tuned against the
# evaluation set and recorded under scoring_version — the labeled set is still
# empty, so this number has NOT been validated against real model output.
#
# It is not picked by feel either: tests/test_recover.py measures the similarity
# of every must-recover and must-reject case and asserts the two groups do not
# overlap. This value sits in the gap between them. If a future case narrows that
# gap to nothing, the test fails and says so rather than silently misclassifying.
FUZZY_THRESHOLD = 0.90

_TOKEN = re.compile(r"\S+")


@dataclass(frozen=True)
class Recovered:
    """A validated span. `excerpt` is the source substring, never the model's."""

    start: int
    end: int
    excerpt: str
    method: Literal["exact", "exact_ambiguous", "fuzzy"]
    similarity: float


@dataclass(frozen=True)
class Rejected:
    model_excerpt: str
    best_similarity: float
    reason: Literal["empty", "below_threshold"]


Outcome = Recovered | Rejected


def recover(content: Normalized, model_excerpt: str) -> Outcome:
    """
    Find where the model's excerpt occurs in the submitted content.

    The excerpt is normalized with the SAME normalizer as the content, so the
    differences normalization exists to erase — curly quotes, exotic spaces,
    collapsed whitespace — never reach the comparison.
    """
    haystack = content.text
    needle = normalize(model_excerpt).text

    if not needle or not haystack:
        return _reject(model_excerpt, 0.0, "empty")

    # Case-insensitive, and deliberately so. A model quoting mid-sentence often
    # capitalises the first word; measured, that alone scores 0.853 and would be
    # REJECTED as if it were a paraphrase. Ignoring case cannot display the wrong
    # text, because the excerpt returned is the source substring either way.
    #
    # re.IGNORECASE rather than casefold(): casefolding can change length
    # (ß -> ss), which would silently shift every index after it.
    matches = list(re.finditer(re.escape(needle), haystack, re.IGNORECASE))
    if matches:
        match = matches[0]
        return Recovered(
            start=match.start(),
            end=match.end(),
            excerpt=haystack[match.start() : match.end()],
            # Ambiguity is recorded, not resolved: first hit wins, and the label
            # lets telemetry count how often it happens.
            method="exact" if len(matches) == 1 else "exact_ambiguous",
            similarity=1.0,
        )

    best_score, best_span = _best_window(haystack, needle)
    if best_span is not None and best_score >= FUZZY_THRESHOLD:
        start, end = best_span
        return Recovered(
            start=start,
            end=end,
            # Snapped to the source span. The model's string is discarded here —
            # this is the line that makes a drifted excerpt safe to display.
            excerpt=haystack[start:end],
            method="fuzzy",
            similarity=best_score,
        )

    return _reject(model_excerpt, best_score, "below_threshold")


def _best_window(haystack: str, needle: str) -> tuple[float, tuple[int, int] | None]:
    """
    Token-level sliding window. Windows are whole tokens, so a recovered span
    never starts or ends mid-word.
    """
    tokens = [(match.start(), match.end()) for match in _TOKEN.finditer(haystack)]
    if not tokens:
        return 0.0, None

    needle_tokens = max(1, len(_TOKEN.findall(needle)))
    widths = range(
        max(1, int(needle_tokens * 0.7)),
        min(len(tokens), int(needle_tokens * 1.4) + 2) + 1,
    )

    matcher = SequenceMatcher(autojunk=False)
    matcher.set_seq2(needle)

    best_score = 0.0
    best_span: tuple[int, int] | None = None

    for width in widths:
        for first in range(0, len(tokens) - width + 1):
            start = tokens[first][0]
            end = tokens[first + width - 1][1]
            matcher.set_seq1(haystack[start:end])
            # Cheap upper bounds first; ratio() is the expensive one.
            if matcher.real_quick_ratio() < best_score or matcher.quick_ratio() < best_score:
                continue
            score = matcher.ratio()
            if score > best_score:
                best_score, best_span = score, (start, end)

    return best_score, best_span


def _reject(
    model_excerpt: str, best_similarity: float, reason: Literal["empty", "below_threshold"]
) -> Rejected:
    logger.info(
        "evidence_rejected",
        extra={
            "reason": reason,
            "best_similarity": round(best_similarity, 4),
            "model_excerpt": model_excerpt,
        },
    )
    return Rejected(model_excerpt=model_excerpt, best_similarity=best_similarity, reason=reason)
