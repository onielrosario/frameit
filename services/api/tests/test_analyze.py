"""
POST /analyze end to end, with the model call replaced by recorded outputs.

Steps 06/11 tests carried over from the mock era, now driven through the real
pipeline: every excerpt a client sees has gone through span recovery.

Per CLAUDE.md, a passing test is not evidence. Mutation results for these guards
are recorded in services/api/docs/CONTEXT.md.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.analysis.gemini import UpstreamError
from app.api.routes import get_analyzer
from app.config import API_VERSION, get_settings
from app.evidence.normalize import normalize
from app.main import app
from tests import fakes

client = TestClient(app)

POLICY = "Government must step in to protect vulnerable families."
LONG_POLICY = (
    "Lawmakers returned to the capitol on Monday. " * 6
    + POLICY
    + " Critics refused to even consider the plan, and the reckless cuts would gut the program."
)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def use(outcome):
    dependency = fakes.analyzer(outcome)
    app.dependency_overrides[get_analyzer] = dependency
    return dependency


def _post(content: str, **params: str):
    return client.post("/analyze", json={"content": content}, params=params)


def _classified_output():
    return fakes.output(
        [
            fakes.signal(POLICY, "policy_framing", "left", "strong"),
            fakes.signal("refused to even consider", "loaded_language", "left", "moderate"),
        ]
    )


# --- request handling --------------------------------------------------------


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["api_version"] == API_VERSION


def test_rejects_content_over_the_limit() -> None:
    """The server re-checks the limit rather than trusting the client."""
    dependency = use(fakes.result(fakes.output()))
    limit = get_settings().max_content_chars
    assert _post("x" * (limit + 1)).status_code == 413
    assert dependency.seen == [], "an over-limit submission must never reach the model"


def test_accepts_content_at_exactly_the_limit() -> None:
    """Off-by-one guard: the limit is inclusive."""
    use(fakes.result(fakes.output(is_political=False)))
    limit = get_settings().max_content_chars
    assert _post("x" * limit).status_code == 200


def test_rejects_empty_content() -> None:
    assert client.post("/analyze", json={"content": ""}).status_code == 422


def test_whitespace_only_content_never_reaches_the_model() -> None:
    dependency = use(fakes.result(fakes.output()))
    assert _post("   \n\t  ").status_code == 422
    assert dependency.seen == []


def test_the_model_is_shown_the_normalized_text() -> None:
    """Spans index normalized text, so the model must quote from the same text."""
    dependency = use(fakes.result(fakes.output(is_political=False)))
    raw = "  The  “plan”—it’s   bold.  "
    _post(raw)
    assert dependency.seen == [normalize(raw).text]


def test_mock_query_parameter_is_gone() -> None:
    """Step 06's dev lever was removed at step 12; it must not force a status."""
    use(fakes.result(_classified_output()))
    assert _post(LONG_POLICY, mock="blocked").json()["status"] == "classified"


def test_missing_model_configuration_is_a_503_not_a_result(monkeypatch) -> None:
    """No key means no analysis — never a fabricated or default result."""
    from app import config

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("FRAME_ANALYSIS_MODEL", raising=False)
    config.get_settings.cache_clear()
    try:
        response = _post(LONG_POLICY)
    finally:
        config.get_settings.cache_clear()
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


@pytest.mark.parametrize(
    ("status", "error_class"), [(502, "malformed_output"), (503, "rate_limited"), (504, "timeout")]
)
def test_upstream_failures_are_http_errors_not_statuses(status: int, error_class: str) -> None:
    """
    An operational failure is neither `blocked` (the model refused) nor
    `unclear` (an analytical outcome). Either would corrupt a metric.
    """

    def failing():
        def analyze(text: str):
            raise UpstreamError("upstream failed", status=status, error_class=error_class)

        return analyze

    app.dependency_overrides[get_analyzer] = failing
    response = _post(LONG_POLICY)
    assert response.status_code == status
    assert "status" not in response.json()


# --- the product rules ---------------------------------------------------------


def test_every_excerpt_is_a_real_substring_sliced_by_its_own_span() -> None:
    use(fakes.result(_classified_output()))
    body = _post(LONG_POLICY).json()
    normalized = normalize(LONG_POLICY).text
    assert body["evidence"]
    for item in body["evidence"]:
        start, end = item["span"]["start"], item["span"]["end"]
        assert normalized[start:end] == item["excerpt"]


def test_displayed_excerpt_is_the_source_substring_not_the_model_string() -> None:
    """
    The model re-capitalised and curled the quotes. The client must see what the
    page says, not what the model typed (analysis-contract.md §5).
    """
    content = LONG_POLICY.replace("Government must", 'and "government must')
    model_excerpt = "Government must step in to protect vulnerable families."
    use(fakes.result(fakes.output([fakes.signal(model_excerpt, strength="strong")])))
    body = _post(content).json()
    shown = body["evidence"][0]["excerpt"]
    assert shown != model_excerpt
    assert shown == "government must step in to protect vulnerable families."


def test_fabricated_evidence_never_reaches_the_client() -> None:
    use(
        fakes.result(
            fakes.output(
                [
                    fakes.signal(POLICY, strength="strong"),
                    fakes.signal(
                        "The radical plan will destroy the economy forever.",
                        "fear_framing",
                        "left",
                        "strong",
                    ),
                ]
            )
        )
    )
    body = _post(LONG_POLICY).json()
    excerpts = [item["excerpt"] for item in body["evidence"]]
    assert excerpts == [POLICY]


def test_hallucinated_strong_signal_downgrades_the_result(caplog) -> None:
    """
    architecture.md §4: re-score on survivors. A classification whose second
    independent signal was invented must not keep the band that signal bought.
    """
    use(
        fakes.result(
            fakes.output(
                [
                    fakes.signal(POLICY, "policy_framing", "left", "strong"),
                    fakes.signal(
                        "Invented sentence that is nowhere in the text at all.",
                        "us_vs_them",
                        "left",
                        "strong",
                    ),
                ]
            )
        )
    )
    with caplog.at_level(logging.INFO, logger="frame.telemetry"):
        body = _post(LONG_POLICY).json()
    assert body["classification"]["label"] == "slightly_left"
    record = json.loads(caplog.records[-1].getMessage())
    assert record["downgraded_after_validation"] is True
    assert record["pre_validation_label"] == "strongly_left"


def test_all_evidence_hallucinated_becomes_unclear_not_classified() -> None:
    use(
        fakes.result(
            fakes.output(
                [
                    fakes.signal(
                        "Nothing like this sentence appears in the passage.", strength="strong"
                    ),
                ]
            )
        )
    )
    body = _post(LONG_POLICY).json()
    assert body["status"] == "unclear"
    assert body["evidence"] == []


def test_response_carries_no_model_output_fields() -> None:
    """No client ever sees model output (analysis-contract.md §1)."""
    use(
        fakes.result(
            fakes.output(
                [fakes.signal(POLICY, strength="strong")],
                limitations=["MODEL PROSE THAT MUST NOT SHIP"],
            )
        )
    )
    raw = _post(LONG_POLICY).text
    body = json.loads(raw)
    forbidden = {
        "signals",
        "raw",
        "raw_model_output",
        "model_output",
        "prompt",
        "reasoning",
        "debug",
        "content_assessment",
        "political_issues",
        "direction",
    }
    assert forbidden.isdisjoint(body.keys())
    assert "MODEL PROSE THAT MUST NOT SHIP" not in raw
    assert "test issue" not in raw


def test_propaganda_is_withheld_until_step_15() -> None:
    """A naive prompt's technique findings do not reach a client (methodology §8)."""
    use(
        fakes.result(
            fakes.output(
                [fakes.signal(POLICY, strength="strong")],
                propaganda=[{"technique": "fear_appeal", "excerpt": POLICY, "interpretation": "x"}],
            )
        )
    )
    body = _post(LONG_POLICY).json()
    assert body["propaganda"] is None


def test_classified_response_omits_position() -> None:
    """Q1 tripwire — see services/api/docs/CONTEXT.md. Delete only with the ADR."""
    use(fakes.result(_classified_output()))
    body = _post(LONG_POLICY).json()
    assert body["status"] == "classified"
    assert "position" not in body["classification"]


def test_blocked_status_carries_nothing_but_the_minimum() -> None:
    use(fakes.blocked())
    body = _post(LONG_POLICY).json()
    assert body["status"] == "blocked"
    for absent in ("classification", "evidence", "confidence", "evidence_strength"):
        assert absent not in body


def test_a_refusal_is_never_reported_as_unclear() -> None:
    """architecture.md §8: that would silently inflate the abstention metric."""
    for reason in ("finish_safety", "prompt_safety", "no_candidates", "empty_text"):
        use(fakes.blocked(reason))
        assert _post(LONG_POLICY).json()["status"] == "blocked"


def test_unclear_still_reports_what_was_observed() -> None:
    """An unclear that shows nothing is a product failure (§6)."""
    use(
        fakes.result(
            fakes.output(
                [
                    fakes.signal(POLICY, "policy_framing", "left", "strong"),
                    fakes.signal(
                        "the reckless cuts would gut the program",
                        "loaded_language",
                        "right",
                        "moderate",
                    ),
                ]
            )
        )
    )
    body = _post(LONG_POLICY).json()
    assert body["status"] == "unclear"
    assert "classification" not in body
    assert len(body["evidence"]) == 2


def test_non_political_is_a_distinct_status() -> None:
    use(fakes.result(fakes.output(is_political=False)))
    body = _post("The new phone has a better camera. " * 5).json()
    assert body["status"] == "non_political"
    assert body["evidence"] == []
    assert "classification" not in body


def test_telemetry_never_contains_the_submission(caplog) -> None:
    use(fakes.result(_classified_output()))
    with caplog.at_level(logging.INFO, logger="frame.telemetry"):
        _post(LONG_POLICY)
    line = caplog.records[-1].getMessage()
    assert "vulnerable families" not in line
    assert "refused" not in line
    record = json.loads(line)
    assert {"config_fingerprint", "prompt_version", "status", "latency_ms"} <= record.keys()


def test_spans_index_the_normalized_content_not_the_raw_submission() -> None:
    raw = "  The  “plan”—it’s   bold.\n\nReally bold, they said, again and again and again.  "
    use(fakes.result(fakes.output([fakes.signal("Really bold, they said", strength="strong")])))
    body = _post(raw).json()
    normalized = normalize(raw).text
    item = body["evidence"][0]
    start, end = item["span"]["start"], item["span"]["end"]
    assert item["excerpt"] == normalized[start:end]
    assert item["excerpt"] != raw[start:end], "input must exercise normalization"


def test_response_carries_the_hash_of_the_normalized_content() -> None:
    use(fakes.result(fakes.output(is_political=False)))
    raw = "  Government  must step in — “protect” vulnerable families.  "
    assert normalize(raw).text != raw, "test input must exercise normalization"
    assert _post(raw).json()["meta"]["content_hash"] == normalize(raw).content_hash


def test_submissions_differing_only_in_whitespace_share_a_content_hash() -> None:
    use(fakes.result(fakes.output(is_political=False)))
    first = _post("the  plan is bold").json()
    second = _post("the\tplan is bold").json()
    assert first["meta"]["content_hash"] == second["meta"]["content_hash"]
