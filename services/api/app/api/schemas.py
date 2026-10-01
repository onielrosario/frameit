"""
Request model for POST /analyze.

Response models live in app/models/analysis.py. docs/analysis-contract.md owns
both shapes; nothing here restates it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    content: str = Field(min_length=1)
    source: Literal["chrome", "web", "ios"] = "chrome"
    # Recorded in telemetry on every request. Without it, a regression that only
    # affects old clients is invisible (analysis-contract.md §7).
    client_version: str = "0.0.0"

    # The 5,000-char ceiling is NOT enforced here. It is configurable per
    # deployment, and the contract says the server re-checks rather than trusting
    # a client's own limit — so it is an explicit route check with its own status
    # code, not a schema constraint that reports as a generic 422.
