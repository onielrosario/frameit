"""
Dataset record model.

The format is OWNED by docs/evaluation.md §1. This mirrors it so a malformed
record fails at load rather than halfway through a run.

The dataset lives as JSONL in git (ADR-0004): a label change shows up in a diff,
the dataset version is the git SHA, and a report is reproducible against an exact
dataset state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Status = Literal["classified", "unclear", "non_political"]
Label = Literal[
    "strongly_left",
    "left",
    "slightly_left",
    "center",
    "slightly_right",
    "right",
    "strongly_right",
]
Direction = Literal["left", "right", "none"]
Confidence = Literal["high", "medium", "low"]
ReviewState = Literal["not_reviewed", "in_review", "reviewed", "needs_second_review", "resolved"]

# How the label came to exist. This changes what a number computed from the
# record MEANS, so it is part of the record rather than a note somewhere.
#
#   human_blind                    — a person labeled it with no proposal in front
#                                    of them. The only provenance that supports
#                                    "agreement with our reviewers" unqualified.
#   agent_drafted_human_reviewed   — a model proposed, a person accepted or
#                                    corrected. Anchoring applies: review pulls
#                                    toward agreeing with the proposal.
#   unreviewed                     — nobody has checked it. Not scoreable.
LabelProvenance = Literal["human_blind", "agent_drafted_human_reviewed", "unreviewed"]

# Ordered so band adjacency is an index distance. Direction reversal is a
# different kind of error and is counted separately (§5.3).
LABEL_ORDER: tuple[Label, ...] = (
    "strongly_left",
    "left",
    "slightly_left",
    "center",
    "slightly_right",
    "right",
    "strongly_right",
)


def direction_of(label: Label) -> Direction:
    if label == "center":
        return "none"
    return "left" if "left" in label else "right"


class ExpectedEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str
    excerpt: str


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    input: str
    source_type: Literal["news", "opinion", "social", "non_political", "synthetic"]
    expected_status: Status
    expected_label: Label | None = None
    expected_direction: Direction
    # Band-adjacent answers get partial credit. Scoring "slightly_left" as wrong
    # because the reviewer wrote "center" manufactures a failure out of a
    # legitimate disagreement between adjacent bands (§1).
    acceptable_labels: list[Label] = Field(default_factory=list)
    expected_evidence: list[ExpectedEvidence] = Field(default_factory=list)
    expected_confidence: Confidence | None = None
    expected_propaganda: list[str] = Field(default_factory=list)
    rationale: str
    mirror_of: str | None = None
    split: Literal["dev", "holdout"]
    review_state: ReviewState = "not_reviewed"
    label_provenance: LabelProvenance = "unreviewed"
    reviewers: list[str] = Field(default_factory=list)
    disagreement_note: str | None = None

    @model_validator(mode="after")
    def _check_label_agrees_with_status(self) -> Record:
        if self.expected_status == "classified" and self.expected_label is None:
            raise ValueError(f"{self.id}: classified records need an expected_label")
        if self.expected_status != "classified" and self.expected_label is not None:
            raise ValueError(f"{self.id}: only classified records may carry an expected_label")
        if self.expected_label and direction_of(self.expected_label) != self.expected_direction:
            raise ValueError(
                f"{self.id}: expected_direction {self.expected_direction!r} contradicts "
                f"expected_label {self.expected_label!r}"
            )
        if self.expected_label and self.expected_label not in self.acceptable_labels:
            raise ValueError(f"{self.id}: acceptable_labels must contain expected_label")
        return self


def load(path: Path) -> list[Record]:
    """Load a JSONL split. Blank lines and `//` comment lines are ignored."""
    records: list[Record] = []
    seen: set[str] = set()
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        try:
            record = Record.model_validate(json.loads(stripped))
        except Exception as error:
            raise ValueError(f"{path}:{number}: {error}") from error
        if record.id in seen:
            raise ValueError(f"{path}:{number}: duplicate id {record.id!r}")
        seen.add(record.id)
        records.append(record)
    return records
