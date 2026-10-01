"""
Model outcome → client response. Pure: no network, no clock, no randomness
except the analysis id.

This is where "no client ever sees model output" is enforced by construction:
the response is BUILT from validated parts, never derived by copying or
filtering the model's JSON. Specifically:

- excerpts and spans come from `recover()` — the source substring, never the
  model's string (analysis-contract.md §5);
- label, confidence and strength come from the scoring module — the model emits
  none of them (§2);
- `explanation` and `limitations` are backend templates. The model's own
  `limitations` prose is not forwarded; its `political_issues` are not either;
- the one piece of model prose that does reach a client is each evidence item's
  `interpretation`, which the contract defines as part of a validated item. It is
  length-capped and discarded along with its item if the item fails recovery.
- propaganda is WITHHELD (null) until step 15. The model is asked for it and
  recovered techniques are counted in telemetry, but a naive prompt is the most
  likely place for a false "fear appeal" on ordinary advocacy (methodology §8),
  and a false finding is worse than a missed one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.analysis.gemini import ModelBlocked, ModelOutcome
from app.analysis.model_output import Signal
from app.evidence.normalize import Normalized
from app.evidence.recover import Recovered, recover
from app.models.analysis import (
    AnalysisResponse,
    BlockedResponse,
    Classification,
    ClassifiedResponse,
    EvidenceItem,
    Meta,
    NonPoliticalResponse,
    Span,
    UnclearResponse,
)
from app.scoring.provisional import SHORT_INPUT_WORDS, Score, ScoredSignal, score

MAX_INTERPRETATION_CHARS = 300

_STRENGTH_RANK = {"weak": 0, "moderate": 1, "strong": 2}


@dataclass
class Trace:
    """Telemetry for one analysis. Counts and labels only — never content."""

    signals_proposed: int = 0
    signals_recovered: int = 0
    signals_rejected: int = 0
    recovered_fuzzy: int = 0
    recovered_ambiguous: int = 0
    techniques_proposed: int = 0
    techniques_recovered: int = 0
    items_dropped_by_schema: int = 0
    pre_validation_label: str | None = None
    downgraded_after_validation: bool = False
    unclear_reason: str | None = None
    blocked_reason: str | None = None
    events: list[str] = field(default_factory=list)


def _recover_signals(
    content: Normalized, signals: list[Signal], trace: Trace
) -> list[tuple[Signal, Recovered]]:
    survivors: list[tuple[Signal, Recovered]] = []
    seen: set[tuple[str, int, int]] = set()
    for signal in signals:
        outcome = recover(content, signal.excerpt)
        if not isinstance(outcome, Recovered):
            trace.signals_rejected += 1
            continue
        trace.signals_recovered += 1
        trace.recovered_fuzzy += outcome.method == "fuzzy"
        trace.recovered_ambiguous += outcome.method == "exact_ambiguous"
        key = (signal.category, outcome.start, outcome.end)
        if key in seen:
            continue  # the same observation reported twice is one observation
        seen.add(key)
        survivors.append((signal, outcome))
    return survivors


def _scored(signals: list[Signal]) -> list[ScoredSignal]:
    return [ScoredSignal(s.category, s.direction, s.strength) for s in signals]


def build(content: Normalized, outcome: ModelOutcome) -> tuple[AnalysisResponse, Trace]:
    analysis_id = f"an_{uuid.uuid4().hex[:16]}"
    meta = Meta(content_hash=content.content_hash)
    trace = Trace()

    if isinstance(outcome, ModelBlocked):
        trace.blocked_reason = outcome.reason
        return (
            BlockedResponse(
                analysis_id=analysis_id,
                status="blocked",
                explanation="Frame couldn't analyze this passage.",
                meta=meta,
            ),
            trace,
        )

    output = outcome.output
    assessment = output.content_assessment
    word_count = len(content.text.split())
    trace.items_dropped_by_schema = outcome.items_dropped
    trace.signals_proposed = len(output.signals)
    trace.techniques_proposed = len(output.propaganda)
    trace.techniques_recovered = sum(
        isinstance(recover(content, t.excerpt), Recovered) for t in output.propaganda
    )

    def run(signals: list[Signal]) -> Score:
        return score(
            _scored(signals),
            is_political=assessment.is_political,
            interpretation_risk=assessment.interpretation_risk,
            word_count=word_count,
        )

    # What the result WOULD have been if every excerpt were real. Only for the
    # downgrade telemetry — never returned.
    trace.pre_validation_label = _label_of(run(output.signals))

    survivors = _recover_signals(content, output.signals, trace)
    result = run([signal for signal, _ in survivors])
    trace.unclear_reason = result.unclear_reason

    final_label = _label_of(result)
    if trace.pre_validation_label != final_label and trace.pre_validation_label not in (
        "unclear",
        "non_political",
    ):
        # architecture.md §4: the earliest visible symptom of model drift.
        trace.downgraded_after_validation = True
        trace.events.append("classification_downgraded_after_validation")

    evidence = _evidence(survivors)
    explanation = _explain(result)
    limitations = _limitations(result, word_count)

    if result.status == "non_political":
        return (
            NonPoliticalResponse(
                analysis_id=analysis_id,
                status="non_political",
                confidence=result.confidence,
                evidence_strength="weak",
                explanation=explanation,
                limitations=limitations,
                meta=meta,
            ),
            trace,
        )

    if result.status == "unclear":
        return (
            UnclearResponse(
                analysis_id=analysis_id,
                status="unclear",
                confidence=result.confidence,
                evidence_strength=result.evidence_strength,
                # Unclear still shows what was observed (contract §6).
                evidence=evidence,
                propaganda=None,
                explanation=explanation,
                limitations=limitations,
                meta=meta,
            ),
            trace,
        )

    if result.label is None:  # unreachable: a classified Score always carries a label
        raise RuntimeError("classified score without a label")
    return (
        ClassifiedResponse(
            analysis_id=analysis_id,
            status="classified",
            classification=Classification(label=result.label),
            confidence=result.confidence,
            evidence_strength=result.evidence_strength,
            evidence=evidence,
            propaganda=None,
            explanation=explanation,
            limitations=limitations,
            meta=meta,
        ),
        trace,
    )


def _label_of(result: Score) -> str:
    if result.status == "classified" and result.label is not None:
        return result.label
    return result.status


def _evidence(survivors: list[tuple[Signal, Recovered]]) -> list[EvidenceItem]:
    # Strongest first: the free tier shows only the first item (methodology §6).
    ordered = sorted(survivors, key=lambda pair: (-_STRENGTH_RANK[pair[0].strength], pair[1].start))
    return [
        EvidenceItem(
            category=signal.category,
            excerpt=recovered.excerpt,  # the SOURCE substring
            span=Span(start=recovered.start, end=recovered.end),
            interpretation=_cap(signal.interpretation),
            strength=signal.strength,
        )
        for signal, recovered in ordered
    ]


def _cap(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= MAX_INTERPRETATION_CHARS:
        return text
    return text[: MAX_INTERPRETATION_CHARS - 1].rstrip() + "…"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _explain(result: Score) -> str:
    """Backend templates. Describes validated evidence only; names no one."""
    if result.status == "non_political":
        return "No political framing detected."
    if result.status == "classified":
        if result.direction == "center":
            return (
                f"{_plural(result.independent_categories, 'independent signal')} of framing were "
                "found, and none favors a direction."
            )
        return (
            f"{_plural(result.independent_categories, 'independent framing signal')} in the "
            f"passage {'leans' if result.independent_categories == 1 else 'lean'} {result.direction}."
        )
    return {
        "no_signals": "Insufficient evidence to reliably determine political framing. No framing signal could be located in the passage.",
        "conflicting_directions": "Insufficient evidence to reliably determine political framing. The signals found point in different directions.",
        "interpretation_risk": "This passage may be sarcastic, satirical, fragmentary, or addressed to the analyzer, making political framing unreliable to determine.",
        "insufficient_neutral": "Insufficient evidence to reliably determine political framing. One signal was found, which isn't enough on its own.",
        "short_input_weak_only": "Insufficient evidence to reliably determine political framing. The passage is short and the signals found are weak.",
        "political_but_marked_non_political": "Insufficient evidence to reliably determine political framing.",
    }.get(
        result.unclear_reason or "",
        "Insufficient evidence to reliably determine political framing.",
    )


def _limitations(result: Score, word_count: int) -> list[str]:
    notes = ["Frame analyzed only the selected text, without its surrounding context."]
    if word_count < SHORT_INPUT_WORDS and result.status != "non_political":
        notes.append("Short passages rarely carry enough signal for a confident read.")
    return notes
