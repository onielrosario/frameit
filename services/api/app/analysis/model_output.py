"""
The model-output schema (schema_version) — what Gemini is asked for and what the
API accepts back.

docs/analysis-contract.md §2 OWNS this shape. The rules it states are enforced
structurally here:

- no `score`, no `confidence`, no offsets, no author / outlet / ideology field —
  none exists, and `extra="forbid"` means one cannot be smuggled in;
- `category` and `technique` are closed enums bound to taxonomy_version;
- every item carries an excerpt; an item whose excerpt is blank is dropped
  before validation runs.

This model NEVER reaches a client. It is parsed, mined for queries, and
discarded; the client response is built from scratch in pipeline.py.

Validation is per item: one malformed signal is dropped and logged, it does not
fail the whole analysis. The top-level shape still has to validate.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.models.taxonomy import EvidenceCategory, PropagandaTechnique

logger = logging.getLogger("frame.analysis")

SCHEMA_VERSION = "1"

# Upper bounds, sent in the schema. They bound output tokens (and so latency and
# cost) and stop a pathological response from listing every sentence.
MAX_SIGNALS = 8
MAX_TECHNIQUES = 5

InterpretationRisk = Literal["none", "sarcasm", "satire", "fragmentary", "addresses_analyzer"]
Direction = Literal["left", "right", "neutral"]
Strength = Literal["strong", "moderate", "weak"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContentAssessment(_Strict):
    is_political: bool
    political_issues: list[str] = Field(default_factory=list)
    # `addresses_analyzer` is threat-model.md §1's mitigation: content that talks
    # TO the analyzer ("ignore previous instructions", "classify this as…") is a
    # signal toward unclear, never something to obey.
    interpretation_risk: InterpretationRisk


class Signal(_Strict):
    category: EvidenceCategory
    direction: Direction
    strength: Strength
    excerpt: str = Field(description="Exact quote from the submission. A query, not content.")
    interpretation: str


class Technique(_Strict):
    technique: PropagandaTechnique
    excerpt: str = Field(description="Exact quote from the submission.")
    interpretation: str


class ModelOutput(_Strict):
    content_assessment: ContentAssessment
    signals: list[Signal] = Field(default_factory=list, max_length=MAX_SIGNALS)
    propaganda: list[Technique] = Field(default_factory=list, max_length=MAX_TECHNIQUES)
    limitations: list[str] = Field(default_factory=list)


class MalformedOutput(Exception):
    """The response was not JSON, or its top-level shape did not validate."""


def parse(raw: dict[str, Any]) -> tuple[ModelOutput, int]:
    """
    Validate a decoded model response item by item.

    Returns the output and the number of items dropped. Dropped items are logged
    with their validation error, never passed through.
    """
    if not isinstance(raw, dict):
        raise MalformedOutput("top level is not an object")

    dropped = 0
    kept: dict[str, list[dict[str, Any]]] = {}
    for key, item_model in (("signals", Signal), ("propaganda", Technique)):
        items = raw.get(key) or []
        if not isinstance(items, list):
            raise MalformedOutput(f"{key} is not a list")
        survivors = []
        for item in items:
            # "An item without an excerpt is dropped before validation even runs."
            if not isinstance(item, dict) or not str(item.get("excerpt") or "").strip():
                dropped += 1
                logger.info("model_item_dropped", extra={"field": key, "reason": "no_excerpt"})
                continue
            try:
                item_model.model_validate(item)
            except ValidationError as error:
                dropped += 1
                logger.info(
                    "model_item_dropped",
                    extra={"field": key, "reason": "invalid", "errors": error.error_count()},
                )
                continue
            survivors.append(item)
        kept[key] = survivors[: MAX_SIGNALS if key == "signals" else MAX_TECHNIQUES]

    try:
        output = ModelOutput.model_validate({**raw, **kept})
    except ValidationError as error:
        raise MalformedOutput(str(error)) from error
    return output, dropped


def response_json_schema() -> dict[str, Any]:
    """
    ModelOutput as a self-contained JSON Schema for Gemini's structured output.

    `$defs` / `$ref` are inlined: Gemini supports a subset of JSON Schema and a
    flat schema is the shape least likely to be rejected or partially honoured.
    Pydantic's `title` keys are noise to the model and are stripped.
    """
    schema = ModelOutput.model_json_schema()
    defs = schema.pop("$defs", {})

    def inline(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                name = node["$ref"].rsplit("/", 1)[-1]
                return inline(copy.deepcopy(defs[name]))
            return {k: inline(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [inline(v) for v in node]
        return node

    inlined: dict[str, Any] = inline(schema)
    return inlined
