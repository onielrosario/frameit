"""
ASGI entrypoint.

A plain FastAPI application with no Vercel-specific imports — ADR-0002 keeps the
hosting decision reversible, and that only holds if nothing here knows where it
runs. Vercel finds `app` by name; uvicorn runs the same object locally.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings

# Frame's own loggers (telemetry, evidence rejections, model drops) at INFO.
# Structured lines to stderr until Postgres at Milestone 9; Vercel captures them.
_frame_logger = logging.getLogger("frame")
if not _frame_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    _frame_logger.addHandler(_handler)
    _frame_logger.setLevel(logging.INFO)
    _frame_logger.propagate = False

app = FastAPI(title="Frame API", version="0.1.0")

_settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    # Explicit origins, never "*". The pinned extension key (manifest.json)
    # is what makes this list stable across reloads.
    allow_origins=list(_settings.cors_allowed_origins),
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.include_router(router)
