"""
The full version set, and the one place the config fingerprint is computed
(architecture.md §6).

Listing six version fields at each call site guarantees someone eventually
forgets one and serves stale analyses across a prompt change. So nothing else
computes this — the cache (step 18) and telemetry both call `fingerprint()`.
"""

from __future__ import annotations

import hashlib
import json

from app.analysis.gemini import PROMPT_VERSION
from app.analysis.model_output import SCHEMA_VERSION
from app.config import NORMALIZATION_VERSION
from app.models.taxonomy import TAXONOMY_VERSION
from app.scoring.provisional import SCORING_VERSION


def version_set(model_version: str | None) -> dict[str, str]:
    return {
        "model_version": model_version or "unset",
        "prompt_version": PROMPT_VERSION,
        "scoring_version": SCORING_VERSION,
        "taxonomy_version": TAXONOMY_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "schema_version": SCHEMA_VERSION,
    }


def fingerprint(model_version: str | None) -> str:
    canonical = json.dumps(version_set(model_version), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
