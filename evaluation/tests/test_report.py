"""
Report format tests, including a golden file (docs/evaluation.md §6).

A golden file exists so a formatting change cannot look like a quality change in
a diff of committed reports. When it fails, decide which happened before
regenerating it.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import make_outcome, make_record

from frame_eval import report as report_module
from frame_eval.metrics import Prediction

GOLDEN = Path(__file__).parent / "golden" / "report.json"

VERSIONS = report_module.Versions(
    api_version="0",
    normalization_version="0",
    taxonomy_version="0",
    scoring_version="0",
    prompt_version="v0+0000000000",
    schema_version="1",
    analysis_model="<mock>",
    fuzzy_threshold=0.9,
    dataset_sha="0000000000000000000000000000000000000000",
)


def _outcomes():
    left = make_record(id="ev_l", mirror_of="ev_r")
    right = make_record(
        id="ev_r",
        mirror_of="ev_l",
        expected_label="slightly_right",
        expected_direction="right",
        acceptable_labels=["center", "slightly_right"],
    )
    unclear = make_record(
        id="ev_u",
        expected_status="unclear",
        expected_label=None,
        expected_direction="none",
        acceptable_labels=[],
    )
    return [
        make_outcome(
            left,
            Prediction(
                status="classified",
                label="slightly_left",
                confidence="medium",
                evidence=(("policy_framing", "Working families"),),
            ),
        ),
        make_outcome(
            right,
            Prediction(
                status="classified",
                label="strongly_right",
                confidence="high",
                evidence=(("policy_framing", "Working families"),),
            ),
        ),
        make_outcome(
            unclear,
            Prediction(
                status="classified",
                label="center",
                confidence="low",
                evidence=(("loaded_language", "not in the input"),),
            ),
            grounded=[False],
        ),
    ]


def _report():
    return report_module.build(_outcomes(), VERSIONS, "dev", "2026-01-01T00:00:00+00:00")


def test_report_matches_the_golden_file() -> None:
    assert json.loads(GOLDEN.read_text()) == _report(), (
        "Report structure changed. If that was intentional, regenerate the golden file; "
        "if not, this is the bug."
    )


def test_dev_runs_are_labelled_in_sample_in_plain_language() -> None:
    """§7: in-sample numbers are labelled in-sample. No exceptions."""
    markdown = report_module.to_markdown(_report())
    assert "In-sample" in markdown
    assert "not generalisation" in markdown


def test_the_word_accuracy_is_never_used() -> None:
    """§7: say "agreement with our reviewers", never "accuracy"."""
    markdown = report_module.to_markdown(_report()).lower()
    assert "accuracy" not in markdown
    assert "agreement with our reviewers" in markdown


def test_ungrounded_excerpt_is_called_a_release_blocker() -> None:
    """§5.1: a fabricated excerpt is a release blocker, not a backlog item."""
    markdown = report_module.to_markdown(_report())
    assert "RELEASE BLOCKER" in markdown
    assert "not in the input" in markdown


def test_mirror_failures_appear_in_the_summary() -> None:
    """§7: publish mirror-symmetry results including failures."""
    markdown = report_module.to_markdown(_report())
    assert "0/1 pairs symmetric" in markdown
    assert "ev_l / ev_r" in markdown


def test_sample_size_is_always_stated() -> None:
    assert "3 examples" in report_module.to_markdown(_report())


def test_agent_drafted_labels_are_disclosed_in_the_summary() -> None:
    """
    §7: say what the number is. A run with no blind-labeled records must not
    present its agreement sections as agreement with a reviewer's own judgment.
    """
    outcomes = _outcomes()
    for outcome in outcomes:
        object.__setattr__(outcome.record, "label_provenance", "agent_drafted_human_reviewed")

    built = report_module.build(outcomes, VERSIONS, "dev", "2026-01-01T00:00:00+00:00")
    markdown = report_module.to_markdown(built)

    assert built["blind_labeled"] == 0
    assert "No blind-labeled records in this run" in markdown
    assert "agreement with a reviewer who saw a proposal" in markdown
    # Grounding does not depend on labels and must not be caveated away with them.
    assert "Evidence grounding is unaffected" in markdown


def test_mixed_provenance_says_how_many_are_blind() -> None:
    outcomes = _outcomes()
    object.__setattr__(outcomes[0].record, "label_provenance", "agent_drafted_human_reviewed")
    built = report_module.build(outcomes, VERSIONS, "dev", "2026-01-01T00:00:00+00:00")
    assert "2/3 records are blind-labeled" in report_module.to_markdown(built)
