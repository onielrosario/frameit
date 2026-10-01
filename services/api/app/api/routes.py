"""
POST /analyze — the request lifecycle in architecture.md §4, as far as step 12.

    validate → enforce limit → NORMALIZE → content_hash
    → [rate limit, spend breaker, cache: step 18]
    → Gemini (structured output) → refusal/safety → blocked
    → schema validation → SPAN RECOVERY → score on survivors only
    → telemetry (no content) → return

The step-06 `?mock=` parameter is gone. Tests exercise every branch by
overriding the `get_analyzer` dependency with recorded model outputs instead.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException

from app.analysis import pipeline
from app.analysis.gemini import GeminiAnalyzer, ModelBlocked, ModelOutcome, UpstreamError
from app.api.schemas import AnalyzeRequest
from app.config import API_VERSION, get_settings
from app.evidence.normalize import normalize
from app.models.analysis import AnalysisResponse
from app.versions import fingerprint, version_set

router = APIRouter()
telemetry = logging.getLogger("frame.telemetry")

Analyzer = Callable[[str], tuple[ModelOutcome, float]]


def get_analyzer() -> Analyzer:
    """
    The model call, as a dependency so tests substitute recorded outputs.

    Construction is deferred to call time so a missing key is a 503 on
    /analyze, not a crash at import — /health keeps answering either way.
    """
    settings = get_settings()

    def analyze(text: str) -> tuple[ModelOutcome, float]:
        return GeminiAnalyzer(settings.gemini_api_key, settings.analysis_model)(text)

    return analyze


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "api_version": API_VERSION}


@router.post("/analyze", response_model=AnalysisResponse)
def analyze(
    request: AnalyzeRequest, analyzer: Analyzer = Depends(get_analyzer)
) -> AnalysisResponse:
    # A plain `def`: FastAPI runs it in a worker thread, so the blocking model
    # call does not stall the event loop for concurrent requests.
    settings = get_settings()
    started = time.perf_counter()

    # The server re-checks the limit; a client's own cap is a courtesy (§3).
    if len(request.content) > settings.max_content_chars:
        raise HTTPException(
            status_code=413,
            detail=(
                f"content exceeds {settings.max_content_chars} characters "
                f"(received {len(request.content)})"
            ),
        )

    # Normalize once. Spans index the NORMALIZED text (contract §5), the model
    # is shown the normalized text, and recover() searches the same object.
    normalized = normalize(request.content)
    if not normalized.text:
        raise HTTPException(status_code=422, detail="content is empty after normalization")

    record: dict[str, object] = {
        "event": "analysis",
        "client_version": request.client_version,
        "source": request.source,
        "input_chars": len(normalized.text),
        "input_words": len(normalized.text.split()),
        **version_set(settings.analysis_model),
        "config_fingerprint": fingerprint(settings.analysis_model),
        "cached": False,
    }

    try:
        outcome, llm_ms = analyzer(normalized.text)
    except UpstreamError as error:
        record.update(
            status="error",
            error_class=error.error_class,
            latency_ms=round((time.perf_counter() - started) * 1000),
        )
        _emit(record)
        raise HTTPException(status_code=error.status, detail=str(error)) from error

    response, trace = pipeline.build(normalized, outcome)

    record.update(
        analysis_id=response.analysis_id,
        status=response.status,
        latency_ms=round((time.perf_counter() - started) * 1000),
        llm_latency_ms=round(llm_ms),
        model_version_reported=outcome.model_version,
        prompt_tokens=outcome.usage.prompt_tokens,
        output_tokens=outcome.usage.output_tokens,
        thinking_tokens=outcome.usage.thinking_tokens,
        **{k: v for k, v in vars(trace).items() if v not in (None, [], 0, False)},
    )
    if response.status == "classified":
        record.update(
            label=response.classification.label,
            confidence=response.confidence,
            evidence_strength=response.evidence_strength,
        )
    if isinstance(outcome, ModelBlocked):
        record["blocked_reason"] = outcome.reason
    _emit(record)
    return response


def _emit(record: dict[str, object]) -> None:
    """
    One structured line per analysis, written inside the request — never
    deferred to shutdown, which Fluid caps at ~500ms (architecture.md §3).
    Contains no submitted content and no model excerpts.
    """
    telemetry.info(json.dumps(record, default=str, sort_keys=True))
