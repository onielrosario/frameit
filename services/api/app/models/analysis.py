"""
Response models for the client contract.

Mirrors docs/analysis-contract.md §3, which OWNS these shapes. Nothing here
restates its rules; the models enforce them.

Design note — why four models instead of one with optional fields:

§3 gives each status a different shape. `classification` is present only when
status is "classified"; `blocked` carries nothing but status, analysis_id and
explanation; `non_political` has empty evidence and no classification. A single
model with everything optional can represent all of those, and also represents
every shape the contract forbids — a blocked response carrying a classification,
an unclear one with a label. A discriminated union cannot express those at all.

The contract's rules become unrepresentable states rather than assertions
somebody has to remember to write.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.config import API_VERSION

# Closed enums bound to taxonomy_version (§2), defined once in taxonomy.py and
# shared with the model-output schema. An unknown value is a validation failure
# here, never a passthrough — the server is strict so the client can be tolerant.
# §7 asks clients to degrade gracefully on values a NEWER server sends, which is
# not the same as this server inventing one.
from app.models.taxonomy import EvidenceCategory, PropagandaTechnique

ClassificationLabel = Literal[
    "strongly_left",
    "left",
    "slightly_left",
    "center",
    "slightly_right",
    "right",
    "strongly_right",
]
Confidence = Literal["high", "medium", "low"]
Strength = Literal["strong", "moderate", "weak"]
PropagandaLevel = Literal["none", "low", "moderate", "high"]


class Strict(BaseModel):
    """
    extra="forbid" on every response model.

    This is the structural half of "no client ever sees model output" (§1). A
    stray `signals` or `raw` key cannot be added by accident — it raises.
    """

    model_config = ConfigDict(extra="forbid")


class Span(Strict):
    """Half-open [start, end) into the NORMALIZED content (§5)."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)


class EvidenceItem(Strict):
    category: EvidenceCategory
    # Always normalized_content[start:end] — the source substring, never the
    # model's string. Enforced at construction by the evidence module (step 10),
    # not here; this model cannot see the content.
    excerpt: str
    span: Span
    interpretation: str
    strength: Strength


class PropagandaTechniqueItem(Strict):
    technique: PropagandaTechnique
    excerpt: str
    span: Span


class Propaganda(Strict):
    level: PropagandaLevel
    techniques: list[PropagandaTechniqueItem]


class Meta(Strict):
    cached: bool = False
    # sha256 of the NORMALIZED content (§5). Lets a client confirm a response
    # applies to the text it submitted rather than to a cached analysis of
    # something else. It does NOT let a client verify excerpt-against-span: that
    # needs the normalized text, and the normalizer is server-side only.
    content_hash: str | None = None
    # Ships before it is needed. It cannot be added retroactively to clients
    # already in the wild (§7).
    min_supported_client: str = "0.1.0"


class Classification(Strict):
    label: ClassificationLabel
    # `position` is deliberately absent. Q1 is open (§4); omitting is the
    # reversible direction, since adding an optional field stays backward
    # compatible within an api_version and removing one does not (§7).


class _Base(Strict):
    api_version: str = API_VERSION
    analysis_id: str
    explanation: str
    meta: Meta = Field(default_factory=Meta)


class ClassifiedResponse(_Base):
    status: Literal["classified"]
    classification: Classification
    confidence: Confidence
    evidence_strength: Strength
    evidence: list[EvidenceItem]
    propaganda: Propaganda | None = None
    limitations: list[str] = Field(default_factory=list)


class UnclearResponse(_Base):
    status: Literal["unclear"]
    # No `classification` field exists on this model at all — an unclear result
    # carrying a label is not a bug to catch, it is unconstructible.
    confidence: Confidence
    evidence_strength: Strength
    # May be non-empty: unclear still shows what was observed (§6).
    evidence: list[EvidenceItem]
    propaganda: Propaganda | None = None
    limitations: list[str] = Field(default_factory=list)


class NonPoliticalResponse(_Base):
    status: Literal["non_political"]
    confidence: Confidence
    evidence_strength: Strength
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=0)
    propaganda: None = None
    limitations: list[str] = Field(default_factory=list)


class BlockedResponse(_Base):
    """
    A reliability event, not an analytical outcome (§3).

    Everything absent except status, analysis_id, explanation (and meta). The
    fields simply do not exist on this model.
    """

    status: Literal["blocked"]


AnalysisResponse = Annotated[
    ClassifiedResponse | UnclearResponse | NonPoliticalResponse | BlockedResponse,
    Field(discriminator="status"),
]
