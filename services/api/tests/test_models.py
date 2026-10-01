"""
Step 08: the contract's rules as unconstructible states.

Each test below tries to build a response the contract forbids. If Pydantic
raises, the rule is structural — nobody has to remember it. If it constructs,
the rule was only ever a comment.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from app.models.analysis import (
    AnalysisResponse,
    BlockedResponse,
    Classification,
    ClassifiedResponse,
    EvidenceItem,
    NonPoliticalResponse,
    Span,
    UnclearResponse,
)

adapter = TypeAdapter(AnalysisResponse)


def _evidence() -> EvidenceItem:
    return EvidenceItem(
        category="policy_framing",
        excerpt="Government must step in",
        span=Span(start=0, end=23),
        interpretation="…",
        strength="moderate",
    )


def test_blocked_cannot_carry_a_classification() -> None:
    """blocked is a reliability event, not an analytical outcome (§3)."""
    with pytest.raises(ValidationError):
        BlockedResponse(
            analysis_id="an_1",
            status="blocked",
            explanation="…",
            classification=Classification(label="center"),
        )


def test_blocked_cannot_carry_evidence() -> None:
    with pytest.raises(ValidationError):
        BlockedResponse(
            analysis_id="an_1", status="blocked", explanation="…", evidence=[_evidence()]
        )


def test_unclear_cannot_carry_a_classification() -> None:
    """An unclear result with a label would contradict its own status (§3)."""
    with pytest.raises(ValidationError):
        UnclearResponse(
            analysis_id="an_1",
            status="unclear",
            confidence="low",
            evidence_strength="weak",
            evidence=[],
            explanation="…",
            classification=Classification(label="left"),
        )


def test_unclear_may_carry_evidence() -> None:
    """The opposite rule: unclear must still be able to show what was observed (§6)."""
    response = UnclearResponse(
        analysis_id="an_1",
        status="unclear",
        confidence="low",
        evidence_strength="weak",
        evidence=[_evidence()],
        explanation="…",
    )
    assert len(response.evidence) == 1


def test_non_political_cannot_carry_evidence() -> None:
    with pytest.raises(ValidationError):
        NonPoliticalResponse(
            analysis_id="an_1",
            status="non_political",
            confidence="high",
            evidence_strength="weak",
            evidence=[_evidence()],
            explanation="…",
        )


def test_classification_cannot_carry_position() -> None:
    """
    Q1 is open. Omitting `position` is the reversible direction (§7), so the
    model has no such field. If Q1 is settled the other way, this test is
    deleted deliberately alongside the ADR that settles it.
    """
    with pytest.raises(ValidationError):
        Classification(label="slightly_left", position=-0.35)


def test_no_model_output_can_be_attached() -> None:
    """
    The structural half of "no client ever sees model output" (§1): extra keys
    raise rather than ship.
    """
    with pytest.raises(ValidationError):
        ClassifiedResponse(
            analysis_id="an_1",
            status="classified",
            classification=Classification(label="center"),
            confidence="medium",
            evidence_strength="moderate",
            evidence=[],
            explanation="…",
            signals=[{"raw": "model prose"}],
        )


def test_unknown_category_is_a_validation_failure_not_a_passthrough() -> None:
    """
    Closed enums bound to taxonomy_version (§2). The server is strict so clients
    can afford to be tolerant.
    """
    with pytest.raises(ValidationError):
        EvidenceItem(
            category="vibes",
            excerpt="…",
            span=Span(start=0, end=1),
            interpretation="…",
            strength="moderate",
        )


def test_span_rejects_a_negative_start() -> None:
    with pytest.raises(ValidationError):
        Span(start=-1, end=5)


def test_union_discriminates_on_status() -> None:
    """A client parsing by `status` gets the matching shape, not a guess."""
    parsed = adapter.validate_python(
        {
            "api_version": "0",
            "analysis_id": "an_1",
            "status": "blocked",
            "explanation": "…",
            "meta": {"cached": False, "min_supported_client": "0.1.0"},
        }
    )
    assert isinstance(parsed, BlockedResponse)
