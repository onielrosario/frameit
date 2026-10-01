"""
Environment-derived configuration.

Read once into a frozen dataclass. Fluid compute runs concurrent invocations
inside one instance, so module-level MUTABLE state is shared across requests
(architecture.md §3). Frozen is safe; a dict someone later appends to is not.

No Vercel-specific imports anywhere in this package — ADR-0002's escape hatch
depends on it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

# The contract's api_version (analysis-contract.md §3). Not the package version.
API_VERSION = "0"

# Bumped when the normalizer changes, because offsets and cache entries change
# with it (architecture.md §4). Folded into the config fingerprint (app/versions.py).
NORMALIZATION_VERSION = "0"

DEFAULT_MAX_CONTENT_CHARS = 5_000

# The pinned dev extension origin (apps/extension/manifest.json `key`).
DEFAULT_DEV_ORIGIN = "chrome-extension://bjmnmjlmiffncikflnabhbnjgipfkipo"


@dataclass(frozen=True)
class Settings:
    max_content_chars: int
    cors_allowed_origins: tuple[str, ...] = field(default=())
    analysis_model: str | None = None
    # repr=False: a Settings object that ends up in a log line or a traceback
    # must not print the key.
    gemini_api_key: str | None = field(default=None, repr=False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    raw_origins = os.getenv("FRAME_CORS_ALLOWED_ORIGINS", "").strip()
    origins = (
        tuple(part.strip() for part in raw_origins.split(",") if part.strip())
        if raw_origins
        else (DEFAULT_DEV_ORIGIN,)
    )
    return Settings(
        max_content_chars=int(os.getenv("FRAME_MAX_CONTENT_CHARS", str(DEFAULT_MAX_CONTENT_CHARS))),
        cors_allowed_origins=origins,
        # Model is configuration, never a literal (architecture.md §8).
        analysis_model=os.getenv("FRAME_ANALYSIS_MODEL") or None,
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
    )
