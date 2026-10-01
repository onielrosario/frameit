"""
Normalizer tests.

Per services/api/docs/CONTEXT.md the standard here is round-trip property tests:
for every normalized index, mapping back to the original and slicing must return
the characters that produced it. Example-based tests alone would miss the cases
that matter, which are the ones where lengths change.
"""

from __future__ import annotations

import random

import pytest

from app.evidence.normalize import normalize


def test_nfc_composes_and_maps_back_to_both_source_characters() -> None:
    """ "e" + combining acute is two characters in, one out. The map must say so."""
    original = "café"  # cafe + U+0301
    result = normalize(original)
    assert result.text == "café"
    start, end = result.to_original_span(3, 4)
    assert original[start:end] == "é"
    assert end - start == 2


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("“quoted”", '"quoted"'),
        ("it’s", "it's"),
        ("«guillemets»", '"guillemets"'),
        ("em—dash", "em-dash"),
        ("en–dash", "en-dash"),
        ("minus−sign", "minus-sign"),
    ],
)
def test_character_folds(original: str, expected: str) -> None:
    assert normalize(original).text == expected


@pytest.mark.parametrize("space", [" ", " ", " ", "　", " "])
def test_exotic_spaces_fold_to_u0020(space: str) -> None:
    assert normalize(f"a{space}b").text == "a b"


def test_whitespace_runs_collapse_and_the_span_covers_the_whole_run() -> None:
    original = "alpha \t\n\n  beta"
    result = normalize(original)
    assert result.text == "alpha beta"

    space_index = result.text.index(" ")
    start, end = result.to_original_span(space_index, space_index + 1)
    # The highlight must cover what the reader selected, not what survived folding.
    assert original[start:end] == " \t\n\n  "


def test_leading_and_trailing_whitespace_is_trimmed() -> None:
    result = normalize("\n\n  hello  \t\n")
    assert result.text == "hello"
    start, end = result.to_original_span(0, 5)
    assert result.original[start:end] == "hello"


def test_zero_width_characters_are_dropped_not_folded_to_a_space() -> None:
    """Folding them to a space would invent a word boundary nobody saw."""
    assert normalize("wo​rd").text == "word"
    assert normalize("﻿word").text == "word"


def test_zero_width_joiner_is_preserved() -> None:
    """U+200D is load-bearing inside emoji sequences; dropping it corrupts them."""
    family = "\U0001f468‍\U0001f469‍\U0001f467"
    assert "‍" in normalize(family).text


# --------------------------------------------------------------------------
# Properties. These are the tests that actually guard the map.
# --------------------------------------------------------------------------

SAMPLES = [
    "",
    "   ",
    "plain text",
    "  The “plan”—it’s   bold.\n\nReally bold.  ",
    "café   naı̈ve",
    "tabs\tand\nnewlines\r\nmixed",
    "zero​width﻿marks",
    "“nested ‘quotes’ here”",
    "a" * 300 + "   " + "b" * 300,
]


@pytest.mark.parametrize("original", SAMPLES)
def test_map_is_monotonic_and_non_overlapping(original: str) -> None:
    result = normalize(original)
    assert len(result.starts) == len(result.ends) == len(result.text)
    for index in range(len(result.text)):
        assert result.starts[index] < result.ends[index], "every character has a source"
        if index == 0:
            continue
        previous = (result.starts[index - 1], result.ends[index - 1])
        current = (result.starts[index], result.ends[index])
        # Ranges advance, except when NFC composed a cluster into fewer
        # characters than it contained — then those characters share one source
        # range, because none of them came from part of it.
        assert current[0] >= previous[1] or current == previous, (
            f"index {index}: {current} overlaps {previous} without sharing it"
        )


@pytest.mark.parametrize("original", SAMPLES)
def test_every_character_maps_to_source_that_produces_it(original: str) -> None:
    """
    The round-trip property, per character: slicing the original by the map and
    re-normalizing must yield that character — or, for a collapsed space, a run
    that is entirely whitespace.
    """
    result = normalize(original)

    # Characters sharing one source range came from a single composed cluster and
    # must be checked together: individually, neither half of a decomposed pair
    # normalizes to itself.
    index = 0
    while index < len(result.text):
        span = (result.starts[index], result.ends[index])
        group_end = index
        while (
            group_end + 1 < len(result.text)
            and (result.starts[group_end + 1], result.ends[group_end + 1]) == span
        ):
            group_end += 1

        produced = result.text[index : group_end + 1]
        source = original[span[0] : span[1]]

        if produced.strip() == "":
            assert source.strip() == "", f"index {index}: space maps to non-whitespace {source!r}"
        else:
            assert normalize(source).text == produced, f"index {index}: {source!r} -> {produced!r}"
        index = group_end + 1


@pytest.mark.parametrize("original", SAMPLES)
def test_spans_round_trip(original: str) -> None:
    """
    For spans that begin and end on non-space characters, slicing the original by
    the mapped span and re-normalizing must reproduce the normalized slice
    exactly. Spans touching a space are excluded only because re-normalizing a
    slice trims its own edges, which is a property of the test, not the map.
    """
    result = normalize(original)
    text = result.text
    if len(text) < 2:
        pytest.skip("nothing to span")

    random.seed(len(original))
    for _ in range(60):
        start = random.randrange(0, len(text) - 1)
        end = random.randrange(start + 1, len(text) + 1)
        if text[start] == " " or text[end - 1] == " ":
            continue
        origin_start, origin_end = result.to_original_span(start, end)
        assert normalize(original[origin_start:origin_end]).text == text[start:end]


def test_to_original_span_rejects_spans_outside_the_text() -> None:
    result = normalize("hello")
    for start, end in [(-1, 2), (0, 99), (3, 3), (4, 2)]:
        with pytest.raises(ValueError):
            result.to_original_span(start, end)


def test_content_hash_is_of_the_normalized_text() -> None:
    """
    Two submissions that normalize identically must cache-hit each other; the
    hash is over the normalized text, not the raw submission (architecture.md §4).
    """
    assert normalize("the  plan").content_hash == normalize("the\tplan").content_hash
    assert normalize("the plan").content_hash != normalize("the plans").content_hash


def test_selection_text_substitution_survives_normalization() -> None:
    """
    The stage-04 finding, carried into the backend.

    Chrome's `info.selectionText` replaces U+000A with U+0020 at unchanged length
    (apps/extension/docs/CONTEXT.md). Normalization collapses whitespace runs, so
    both sources converge on the same normalized text and the same content hash.

    This is the test that says how much that finding actually costs us.
    """
    from_page = "First paragraph.\n\nSecond paragraph."
    from_menu = from_page.replace("\n", " ")

    assert normalize(from_page).text == normalize(from_menu).text
    assert normalize(from_page).content_hash == normalize(from_menu).content_hash


def test_non_composing_cluster_maps_one_character_at_a_time() -> None:
    """
    "ı" + U+0308 has no precomposed form, so NFC returns both characters
    unchanged. Each must map to its own source character.

    Mapping both to the whole cluster is not wrong so much as imprecise: a span
    covering only the base character would widen to include the mark, and a
    highlight would cover more than the evidence. Caught incidentally by
    test_spans_round_trip; asserted directly here so the coverage is deliberate.
    """
    original = "na\u0131\u0308ve"  # dotless i + combining diaeresis
    result = normalize(original)
    base = result.text.index("\u0131")

    assert result.to_original_span(base, base + 1) == (2, 3)
    assert result.to_original_span(base + 1, base + 2) == (3, 4)


def test_composing_cluster_maps_to_the_whole_cluster() -> None:
    """The opposite case: "e" + U+0301 composes, so the single output character
    genuinely came from both input characters and the span must cover both."""
    result = normalize("cafe\u0301")  # e + combining acute
    assert result.text == "caf\u00e9"
    assert result.to_original_span(3, 4) == (3, 5)
