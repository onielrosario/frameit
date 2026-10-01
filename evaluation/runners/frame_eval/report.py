"""
Report structure and markdown summary (docs/evaluation.md §6, §7).

Every report records the full version set, not just a fingerprint, plus the
dataset git SHA — so comparing two runs is a diff, and a number can always be
traced to the exact code and data that produced it.

The honesty rules in §7 are enforced here rather than left to whoever writes the
summary: sample size is always stated, dev-only runs are labelled in-sample in
plain language, and the word "accuracy" does not appear.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from frame_eval import metrics


@dataclass(frozen=True)
class Versions:
    api_version: str
    normalization_version: str
    taxonomy_version: str
    scoring_version: str
    prompt_version: str
    schema_version: str
    analysis_model: str
    fuzzy_threshold: float
    dataset_sha: str


def build(
    outcomes: list[metrics.Outcome],
    versions: Versions,
    split: str,
    generated_at: str,
) -> dict[str, Any]:
    grounding = metrics.grounding(outcomes)
    abstention = metrics.abstention(outcomes)
    directional = metrics.directional_agreement(outcomes)
    techniques = metrics.propaganda_agreement(outcomes)
    mirrors = metrics.mirror_symmetry(outcomes)

    provenance: dict[str, int] = {}
    for outcome in outcomes:
        key = outcome.record.label_provenance
        provenance[key] = provenance.get(key, 0) + 1

    return {
        "generated_at": generated_at,
        "split": split,
        # §2.3 / §7: a dev-only run is in-sample and must say so in plain language.
        "in_sample": split == "dev",
        "sample_size": len(outcomes),
        # Agreement metrics mean different things depending on how the labels were
        # made. Carried in the report so the qualifier cannot be lost between the
        # run and whoever quotes the number (§7).
        "label_provenance": provenance,
        "blind_labeled": provenance.get("human_blind", 0),
        "versions": {
            "api_version": versions.api_version,
            "normalization_version": versions.normalization_version,
            "taxonomy_version": versions.taxonomy_version,
            "scoring_version": versions.scoring_version,
            "prompt_version": versions.prompt_version,
            "schema_version": versions.schema_version,
            "analysis_model": versions.analysis_model,
            "fuzzy_threshold": versions.fuzzy_threshold,
            "dataset_sha": versions.dataset_sha,
        },
        "evidence_grounding": {
            "grounded": grounding.grounded,
            "total": grounding.total,
            "rate": grounding.rate,
            "ungrounded": [
                {"record_id": record_id, "excerpt": excerpt}
                for record_id, excerpt in grounding.ungrounded_examples
            ],
        },
        "abstention": {
            "correct": abstention.correct,
            "over": abstention.over,
            "under": abstention.under,
            "not_applicable": abstention.not_applicable,
        },
        "directional_agreement": {
            "exact": directional.exact,
            "band_adjacent": directional.band_adjacent,
            "other_same_direction": directional.other_same_direction,
            "reversal": directional.reversal,
            "total": directional.total,
            "agreement_rate": directional.agreement_rate,
        },
        "propaganda": {
            name: {
                "true_positive": score.true_positive,
                "false_positive": score.false_positive,
                "false_negative": score.false_negative,
                "precision": score.precision,
                "recall": score.recall,
            }
            for name, score in sorted(techniques.items())
        },
        "mirror_symmetry": {
            "pairs": len(mirrors),
            "passed": sum(1 for mirror in mirrors if mirror.passed),
            "failures": [
                {
                    "pair": list(mirror.pair),
                    "label_symmetric": mirror.label_symmetric,
                    "confidence_within_one_band": mirror.confidence_within_one_band,
                    "propaganda_matches": mirror.propaganda_matches,
                    "categories_match": mirror.categories_match,
                }
                for mirror in mirrors
                if not mirror.passed
            ],
        },
        "errors": [
            {"record_id": outcome.record.id, "error": outcome.prediction.error}
            for outcome in outcomes
            if outcome.prediction.error
        ],
    }


def _agreement_caveat(report: dict[str, Any]) -> str:
    """
    §7: say what the number is. A label a reviewer wrote from scratch and one a
    reviewer accepted from a model's proposal are different measurements, and the
    second is pulled toward agreement by anchoring.
    """
    blind = report["blind_labeled"]
    total = report["sample_size"]
    if total and blind == 0:
        return (
            "**No blind-labeled records in this run.** Every label here was drafted by an agent "
            "and reviewed by a person, so the agreement sections below measure agreement with a "
            "reviewer who saw a proposal — not blind agreement. Evidence grounding is unaffected: "
            "it is measured against the submitted text, not against a label."
        )
    if blind < total:
        return (
            f"{blind}/{total} records are blind-labeled; the rest were agent-drafted and "
            "reviewed. Agreement below mixes the two."
        )
    return (
        "These are **agreement with our reviewers**. There is no external ground truth for how a "
        "passage frames an issue — only inter-reviewer agreement."
    )


def to_markdown(report: dict[str, Any]) -> str:
    grounding = report["evidence_grounding"]
    directional = report["directional_agreement"]
    abstention = report["abstention"]
    mirrors = report["mirror_symmetry"]

    lines = [
        f"# Frame evaluation — {report['split']} split",
        "",
        f"{report['sample_size']} examples. "
        + (
            "**In-sample**: this split is tuned against, so these numbers describe fit, "
            "not generalisation."
            if report["in_sample"]
            else "Holdout split."
        ),
        "",
        _agreement_caveat(report),
        "",
        "## Evidence grounding (hard gate)",
        "",
        f"{grounding['grounded']}/{grounding['total']} displayed excerpts exist in the submission"
        + (f" — {grounding['rate']:.1%}" if grounding["rate"] is not None else ""),
        "",
    ]
    if grounding["ungrounded"]:
        lines += [
            "**RELEASE BLOCKER.** Excerpts displayed that are not in the submission:",
            "",
            *[f"- `{item['record_id']}`: {item['excerpt']!r}" for item in grounding["ungrounded"]],
            "",
        ]

    lines += [
        "## Abstention",
        "",
        f"- Correct (reviewer unclear, Frame unclear): {abstention['correct']}",
        f"- Over-abstention (reviewer classified, Frame unclear): {abstention['over']}",
        f"- Under-abstention (reviewer unclear, Frame classified): {abstention['under']}",
        "",
        "## Directional agreement",
        "",
        f"- Exact: {directional['exact']}",
        f"- Band-adjacent: {directional['band_adjacent']}",
        f"- Same direction, further off: {directional['other_same_direction']}",
        f"- **Direction reversals: {directional['reversal']}**",
        f"- Scored: {directional['total']}",
        "",
        "## Mirror symmetry",
        "",
        f"{mirrors['passed']}/{mirrors['pairs']} pairs symmetric",
        "",
    ]
    if mirrors["failures"]:
        lines += [
            "Failures are published, not withheld — a published failure is worth more to this "
            "product's credibility than a withheld success:",
            "",
            *[f"- `{' / '.join(failure['pair'])}`" for failure in mirrors["failures"]],
            "",
        ]

    lines += [
        "## Versions",
        "",
        *[f"- `{key}`: {value}" for key, value in report["versions"].items()],
        "",
    ]
    return "\n".join(lines)


def write(report: dict[str, Any], directory: Path, fingerprint: str) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    stem = f"{report['generated_at'].replace(':', '').replace('-', '')}-{fingerprint}"
    json_path = directory / f"{stem}.json"
    markdown_path = directory / f"{stem}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(to_markdown(report), encoding="utf-8")
    return json_path, markdown_path
