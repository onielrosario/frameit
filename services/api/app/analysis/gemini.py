"""
The Gemini call, and the classification of what comes back.

Split in two on purpose:

- `interpret(response)` is PURE. It turns a GenerateContentResponse into one of
  three outcomes and is what the recorded-response tests exercise — refusal,
  safety block, truncation, malformed JSON — with no network.
- `GeminiAnalyzer.__call__` is the only I/O: build the request, send it, hand the
  response to `interpret`.

Outcome semantics (architecture.md §8):

  ModelResult     the model answered in schema.
  ModelBlocked    the model refused or was filtered → status=blocked. NEVER
                  reported as unclear: that would corrupt the abstention metric.
  raises UpstreamError
                  transport failure, quota, timeout, or output that is not the
                  schema. An operational error, surfaced as an HTTP error — not
                  as blocked, so the blocked rate keeps meaning "the model
                  refused", and not as unclear, for the reason above.

No client ever talks to Gemini, and nothing from this module reaches a client
except through pipeline.py, which rebuilds the response from validated parts.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from app.analysis.model_output import MalformedOutput, ModelOutput, parse, response_json_schema

if TYPE_CHECKING:
    # Type-only: the SDK is imported for real inside GeminiAnalyzer.__call__, so
    # importing this module (and running most tests) never loads it.
    from google.genai import types

logger = logging.getLogger("frame.analysis")

PROMPT_PATH = Path(__file__).parent / "prompts" / "analysis_v0.md"
SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")

# Prompts are files in the repo, hashed (architecture.md §6). The version is the
# file's name plus a digest of its bytes, so an edit that forgets to bump the
# name still changes the version — and with it every cache key.
PROMPT_VERSION = f"v0+{hashlib.sha256(SYSTEM_PROMPT.encode('utf-8')).hexdigest()[:10]}"

# Explicit, never the platform default (architecture.md §8). Frame's most
# important inputs — dehumanizing and scapegoating rhetoric — are exactly what a
# hate-speech filter trips on. BLOCK_ONLY_HIGH is a starting point, not a
# measured choice: the blocked rate from real traffic decides whether it moves.
SAFETY_THRESHOLD = "BLOCK_ONLY_HIGH"
SAFETY_CATEGORIES = (
    "HARM_CATEGORY_HARASSMENT",
    "HARM_CATEGORY_HATE_SPEECH",
    "HARM_CATEGORY_DANGEROUS_CONTENT",
    "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "HARM_CATEGORY_CIVIC_INTEGRITY",
)

# Below the extension's 30s client timeout, so the API answers with a real error
# before the client gives up on it.
REQUEST_TIMEOUT_MS = 25_000


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    thinking_tokens: int | None = None


@dataclass(frozen=True)
class ModelResult:
    output: ModelOutput
    items_dropped: int
    model_version: str | None
    usage: Usage
    kind: Literal["result"] = "result"


@dataclass(frozen=True)
class ModelBlocked:
    reason: str
    model_version: str | None
    usage: Usage
    kind: Literal["blocked"] = "blocked"


ModelOutcome = ModelResult | ModelBlocked


class UpstreamError(Exception):
    """The model call failed operationally. `status` is the HTTP code to return."""

    def __init__(self, message: str, *, status: int = 502, error_class: str = "upstream") -> None:
        super().__init__(message)
        self.status = status
        self.error_class = error_class


class ModelNotConfigured(UpstreamError):
    def __init__(self, missing: str) -> None:
        super().__init__(
            f"analysis model is not configured ({missing} is unset)",
            status=503,
            error_class="not_configured",
        )


def build_contents(text: str, marker: str | None = None) -> str:
    """
    Wrap the submission in tags carrying a per-request random marker.

    A fixed `</submission>` could be typed into the page by an attacker to close
    the data block early and continue in the instruction channel. A marker the
    attacker cannot predict cannot be closed (threat-model.md §1 — cheap, and
    partially effective; it is not a solution to injection).
    """
    marker = marker or secrets.token_hex(6)
    return f"<submission-{marker}>\n{text}\n</submission-{marker}>"


def _usage(response: types.GenerateContentResponse) -> Usage:
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return Usage()
    return Usage(
        prompt_tokens=getattr(meta, "prompt_token_count", None),
        output_tokens=getattr(meta, "candidates_token_count", None),
        thinking_tokens=getattr(meta, "thoughts_token_count", None),
    )


def _name(value: object) -> str:
    return str(getattr(value, "name", None) or getattr(value, "value", None) or value)


def interpret(response: types.GenerateContentResponse) -> ModelOutcome:
    """Classify a Gemini response. Pure: no network, no clock."""
    usage = _usage(response)
    model_version = getattr(response, "model_version", None)

    feedback = getattr(response, "prompt_feedback", None)
    if feedback is not None and getattr(feedback, "block_reason", None):
        return ModelBlocked(f"prompt_{_name(feedback.block_reason).lower()}", model_version, usage)

    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return ModelBlocked("no_candidates", model_version, usage)

    candidate = candidates[0]
    finish = _name(getattr(candidate, "finish_reason", None) or "UNSPECIFIED")
    if finish == "MAX_TOKENS":
        # Truncated JSON is not a refusal; it is output we cannot use.
        raise UpstreamError("model output was truncated", error_class="max_tokens")
    if finish != "STOP":
        # SAFETY, RECITATION, PROHIBITED_CONTENT, BLOCKLIST, SPII, OTHER… — the
        # model did not complete an answer for content reasons.
        return ModelBlocked(f"finish_{finish.lower()}", model_version, usage)

    parts = getattr(getattr(candidate, "content", None), "parts", None) or []
    # Thought parts (if thoughts are ever included) are never content.
    text = "".join(
        part.text
        for part in parts
        if getattr(part, "text", None) and not getattr(part, "thought", False)
    )
    if not text.strip():
        return ModelBlocked("empty_text", model_version, usage)

    try:
        decoded = json.loads(text)
        output, dropped = parse(decoded)
    except (json.JSONDecodeError, MalformedOutput) as error:
        raise UpstreamError(
            "model output did not match the analysis schema", error_class="malformed_output"
        ) from error

    return ModelResult(
        output=output, items_dropped=dropped, model_version=model_version, usage=usage
    )


class GeminiAnalyzer:
    """
    One structured-output call per analysis (architecture.md §8).

    A client is created and closed per call. That is deliberate on Fluid compute:
    a pooled client held at module level is shared mutable state across
    concurrent requests and holds sockets from a 1,024-descriptor budget
    (architecture.md §3). The cost is a TLS handshake per analysis.
    """

    def __init__(self, api_key: str | None, model: str | None) -> None:
        if not api_key:
            raise ModelNotConfigured("GEMINI_API_KEY")
        if not model:
            raise ModelNotConfigured("FRAME_ANALYSIS_MODEL")
        self.api_key = api_key
        self.model = model

    def __call__(self, text: str) -> tuple[ModelOutcome, float]:
        """Returns the outcome and the model-call latency in milliseconds."""
        from google import genai
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_json_schema=response_json_schema(),
            # Frame declares no tools; turning AFC off also silences the SDK's
            # per-call warning about it.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            safety_settings=[
                types.SafetySetting(
                    category=types.HarmCategory[category],
                    threshold=types.HarmBlockThreshold[SAFETY_THRESHOLD],
                )
                for category in SAFETY_CATEGORIES
            ],
        )

        started = time.perf_counter()
        client = genai.Client(
            api_key=self.api_key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS)
        )
        try:
            response = client.models.generate_content(
                model=self.model, contents=build_contents(text), config=config
            )
        except errors.ClientError as error:
            code = getattr(error, "code", None)
            if code == 429:
                raise UpstreamError(
                    "analysis capacity is exhausted; try again shortly",
                    status=503,
                    error_class="rate_limited",
                ) from error
            # 400 / 403 / 404: our request or our configuration is wrong. Log the
            # detail server-side; the client gets no upstream text.
            logger.error("gemini_client_error", extra={"code": code, "detail": str(error)[:500]})
            raise UpstreamError(
                "the analysis request was rejected", error_class=f"client_{code}"
            ) from error
        except errors.ServerError as error:
            code = getattr(error, "code", None)
            # Measured 2026-09-29: Gemini returns 503 "high demand" for minutes at
            # a time. That is capacity, not a broken request — tell the client to
            # retry (503), and keep it distinct from our own misconfiguration.
            raise UpstreamError(
                "the analysis model is busy; try again shortly"
                if code == 503
                else "the analysis model is unavailable",
                status=503 if code == 503 else 502,
                error_class="model_overloaded" if code == 503 else "server_error",
            ) from error
        except Exception as error:
            name = type(error).__name__
            timed_out = "timeout" in name.lower()
            raise UpstreamError(
                "the analysis model did not answer in time"
                if timed_out
                else "could not reach the analysis model",
                status=504 if timed_out else 502,
                error_class="timeout" if timed_out else "transport",
            ) from error
        finally:
            client.close()
        latency_ms = (time.perf_counter() - started) * 1000
        return interpret(response), latency_ms
