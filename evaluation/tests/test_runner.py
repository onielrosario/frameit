"""
End-to-end harness test against the mocked analyzer.

§6 requires the runner to be runnable without a model so the harness itself can
be tested without spending tokens. This is that test.
"""

from __future__ import annotations

from conftest import make_record

from frame_eval.cli import mock_analyzer, run


def test_runner_computes_grounding_itself_rather_than_trusting_the_response() -> None:
    record = make_record()
    outcomes = run([record], mock_analyzer)
    assert outcomes[0].grounded == [True]

    def fabricating_analyzer(content: str):
        return {
            "status": "classified",
            "classification": {"label": "center"},
            "confidence": "medium",
            "evidence": [
                {"category": "policy_framing", "excerpt": "text that was never submitted"}
            ],
        }

    fabricated = run([record], fabricating_analyzer)
    assert fabricated[0].grounded == [False], (
        "the runner must check excerpts against the submission itself; a system "
        "reporting its own grounding is not a measurement"
    )


def test_an_analyzer_failure_is_recorded_as_a_datapoint_not_a_crash() -> None:
    def broken_analyzer(content: str):
        raise RuntimeError("connection refused")

    outcomes = run([make_record()], broken_analyzer)
    assert outcomes[0].prediction.status == "error"
    assert "connection refused" in (outcomes[0].prediction.error or "")
