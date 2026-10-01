"""
Normalizer + offset map.

Pure, synchronous, I/O-free (services/api/docs/CONTEXT.md). No network, no model,
no clock — this module is one of the two with hard correctness requirements, and
it must be testable without either.

Normalization is **lossy for display but reversible for offsets**
(architecture.md §4). The map is built in the same pass that does the
normalizing, because deriving it afterwards means re-deriving the decisions.

Without the map, every highlight would be a few characters off in exactly the
texts that needed normalizing most, and it would look like a random,
unreproducible bug.
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass

from app.config import NORMALIZATION_VERSION

# Folds are deliberately 1:1 so the offset map stays a simple index pair per
# character. A fold that expanded one character into two (e.g. "—" -> "--")
# would need a different map shape; none is worth that.
_FOLDS: dict[str, str] = {
    # Apostrophes and single quotes
    "‘": "'",
    "’": "'",
    "‚": "'",
    "‛": "'",
    "′": "'",
    # Double quotes
    "“": '"',
    "”": '"',
    "„": '"',
    "‟": '"',
    "″": '"',
    "«": '"',
    "»": '"',
    # Dashes and the minus sign
    "‐": "-",
    "‑": "-",
    "‒": "-",
    "–": "-",
    "—": "-",
    "―": "-",
    "−": "-",
    # Exotic spaces -> U+0020, then collapsed with everything else
    " ": " ",
    " ": " ",
    " ": " ",
    " ": " ",
    " ": " ",
    " ": " ",
    " ": " ",
    " ": " ",
    " ": " ",
    " ": " ",
    " ": " ",
    " ": " ",
    " ": " ",
    " ": " ",
    " ": " ",
    "　": " ",
}

# Removed outright rather than folded. These carry no text and folding them to a
# space would invent a word boundary that the reader never saw.
#
# NOT included: U+200D zero-width joiner, which is load-bearing inside emoji
# sequences. Dropping it would corrupt them.
_DROPPED = frozenset({"​", "﻿"})


@dataclass(frozen=True)
class Normalized:
    """
    Normalized text plus the map back to the submission.

    `starts[i]` and `ends[i]` bound the original characters that produced
    `text[i]`. They are half-open: `original[starts[i]:ends[i]]`.
    """

    original: str
    text: str
    starts: tuple[int, ...]
    ends: tuple[int, ...]
    version: str = NORMALIZATION_VERSION

    def to_original_span(self, start: int, end: int) -> tuple[int, int]:
        """
        Map a half-open span in the normalized text back to the submission.

        Returns the smallest original range containing the span. For a collapsed
        whitespace run that range covers the whole run, which is what a highlight
        needs — the span is what the reader selected, not what survived folding.
        """
        if not 0 <= start < end <= len(self.text):
            raise ValueError(f"span [{start}, {end}) is outside the normalized text")
        return self.starts[start], self.ends[end - 1]

    @property
    def content_hash(self) -> str:
        """sha256 of the NORMALIZED text (architecture.md §4 lifecycle)."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def normalize(original: str) -> Normalized:
    """
    Apply, in one pass: Unicode NFC, character folds, whitespace-run collapsing,
    and a leading/trailing trim — recording the source range of every character
    emitted.
    """
    chars: list[str] = []
    starts: list[int] = []
    ends: list[int] = []

    for cluster_start, cluster_end, composed in _nfc_clusters(original):
        # When NFC leaves the cluster's length unchanged, nothing composed and
        # each output character has exactly one source character. Mapping them
        # 1:1 keeps the map strictly ordered.
        #
        # "ı" + U+0308 is the case that matters: there is no precomposed form, so
        # NFC returns both characters unchanged. Mapping both to the whole
        # cluster would make two characters claim the same source range.
        one_to_one = len(composed) == cluster_end - cluster_start

        for offset, char in enumerate(composed):
            if one_to_one:
                source_start = cluster_start + offset
                source_end = source_start + 1
            else:
                # Composition happened. The output character came from the whole
                # cluster and cannot be attributed to part of it.
                source_start, source_end = cluster_start, cluster_end

            if char in _DROPPED:
                continue
            folded = _FOLDS.get(char, char)

            if folded.isspace():
                # Extend the run rather than emitting a second space, so the
                # single emitted space maps across the whole original run.
                if chars and chars[-1] == " ":
                    ends[-1] = source_end
                    continue
                chars.append(" ")
            else:
                chars.append(folded)
            starts.append(source_start)
            ends.append(source_end)

    _trim(chars, starts, ends)

    return Normalized(
        original=original,
        text="".join(chars),
        starts=tuple(starts),
        ends=tuple(ends),
    )


def _nfc_clusters(original: str) -> list[tuple[int, int, str]]:
    """
    Split into base-character-plus-combining-marks clusters and NFC each one.

    NFC is applied per cluster rather than to the whole string because it can
    change length — "e" + U+0301 composes to "é" — and a whole-string normalize
    gives no way to know which output characters came from which input ones.
    """
    clusters: list[tuple[int, int, str]] = []
    index = 0
    length = len(original)
    while index < length:
        end = index + 1
        while end < length and unicodedata.combining(original[end]):
            end += 1
        clusters.append((index, end, unicodedata.normalize("NFC", original[index:end])))
        index = end
    return clusters


def _trim(chars: list[str], starts: list[int], ends: list[int]) -> None:
    """Drop leading and trailing spaces, keeping the three lists in step."""
    while chars and chars[0] == " ":
        chars.pop(0)
        starts.pop(0)
        ends.pop(0)
    while chars and chars[-1] == " ":
        chars.pop()
        starts.pop()
        ends.pop()
