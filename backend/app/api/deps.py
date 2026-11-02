"""Shared API dependencies: role guards for read-only demo accounts."""

from __future__ import annotations

import os

from fastapi import Header, HTTPException

DEMO_ROLE = "demo"


def get_current_role(x_role: str | None = Header(default=None)) -> str:
    return (x_role or os.environ.get("DEFAULT_ROLE", "user")).strip().lower()


def require_write(role: str = None):  # type: ignore[override]
    # FastAPI dependency factory
    def _guard(x_role: str | None = Header(default=None)):
        r = (x_role or os.environ.get("DEFAULT_ROLE", "user")).strip().lower()
        if r == DEMO_ROLE:
            # Generic message — do not reveal role/feature gating details (REGO-003).
            raise HTTPException(status_code=403, detail="Forbidden")
        return r

    return _guard


def require_ai(role: str = None):  # type: ignore[override]
    def _guard(x_role: str | None = Header(default=None)):
        r = (x_role or os.environ.get("DEFAULT_ROLE", "user")).strip().lower()
        if r == DEMO_ROLE:
            # Generic message — do not reveal role/feature gating details (REGO-003).
            raise HTTPException(status_code=403, detail="Forbidden")
        return r

    return _guard
