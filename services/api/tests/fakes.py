"""
Test doubles for the model call.

`result(...)` builds a ModelResult from a plain dict exactly as `interpret()`
would, by going through the real `parse()` — so a test cannot hand the pipeline
an output the schema would have rejected.

`gemini_response(...)` builds a google.genai GenerateContentResponse from the
SDK's own model, for the `interpret()` tests. Fixtures marked SYNTHETIC are
hand-built in the SDK's shape; fixtures under tests/recorded/ came from a live
call (see services/api/docs/CONTEXT.md).
"""

from __future__ import annotations

import json
from typing import Any

from app.analysis.gemini import ModelBlocked, ModelResult, Usage
from app.analysis.model_output import parse


def output(
    signals: list[dict[str, Any]] | None = None,
    *,
    is_political: bool = True,
    risk: str = "none",
    propaganda: list[dict[str, Any]] | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "content_assessment": {
            "is_political": is_political,
            "political_issues": ["test issue"] if is_political else [],
            "interpretation_risk": risk,
        },
        "signals": signals or [],
        "propaganda": propaganda or [],
        "limitations": limitations or [],
    }


def signal(
    excerpt: str,
    category: str = "policy_framing",
    direction: str = "left",
    strength: str = "moderate",
    interpretation: str = "Frames the policy as necessary.",
) -> dict[str, Any]:
    return {
        "category": category,
        "direction": direction,
        "strength": strength,
        "excerpt": excerpt,
        "interpretation": interpretation,
    }


def result(raw: dict[str, Any]) -> ModelResult:
    parsed, dropped = parse(raw)
    return ModelResult(output=parsed, items_dropped=dropped, model_version="fake", usage=Usage())


def blocked(reason: str = "finish_safety") -> ModelBlocked:
    return ModelBlocked(reason=reason, model_version="fake", usage=Usage())


def analyzer(outcome):
    """A get_analyzer override that returns a fixed outcome and records its input."""
    seen: list[str] = []

    def analyze(text: str):
        seen.append(text)
        return outcome, 1.0

    def dependency():
        return analyze

    dependency.seen = seen  # type: ignore[attr-defined]
    return dependency


def gemini_response(
    *,
    text: str | dict[str, Any] | None = None,
    finish_reason: str | None = "STOP",
    block_reason: str | None = None,
    candidates: bool = True,
):
    from google.genai import types

    payload: dict[str, Any] = {
        "model_version": "gemini-test",
        "usage_metadata": {"prompt_token_count": 900, "candidates_token_count": 120},
    }
    if block_reason:
        payload["prompt_feedback"] = {"block_reason": block_reason}
    if candidates:
        candidate: dict[str, Any] = {"finish_reason": finish_reason}
        if text is not None:
            body = text if isinstance(text, str) else json.dumps(text)
            candidate["content"] = {"role": "model", "parts": [{"text": body}]}
        payload["candidates"] = [candidate]
    else:
        payload["candidates"] = []
    return types.GenerateContentResponse.model_validate(payload)
