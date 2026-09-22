"""VASS mod-legality endpoint.

POST /api/v1/mod-legality — checks if a modification is legal/non-compliant/
conditional/requires-engineer for a given Australian state/territory.

Mirrors the advisor AI module pattern (deterministic-first, AI fallback).
"""

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, require_ai, require_ai_rate_limit
from app.models.user import User
from app.schemas.mod import ModLegalityRequest, ModLegalityResponse
from app.services.ai_client import mod_legality

router = APIRouter(prefix="/mod-legality", tags=["mod-legality"])


@router.post("", response_model=ModLegalityResponse)
async def check_mod_legality(
    payload: ModLegalityRequest,
    _user: User = Depends(require_ai),
    _: User = Depends(require_ai_rate_limit),
) -> ModLegalityResponse:
    """Check VASS compliance for a single modification.

    Deterministic baseline runs first; 9Router may enrich the summary and
    restrictions with state-specific regulatory context. The is_legal flag,
    status, and confidence are never overridden by the router.
    """
    data = payload.model_dump()
    # Ensure vehicle dict has vehicle_type if present
    if data.get("vehicle") and not data["vehicle"].get("vehicle_type"):
        data["vehicle"]["vehicle_type"] = "car"
    result = await mod_legality(data)
    if not result:
        raise HTTPException(status_code=503, detail="Mod legality engine unavailable")
    return ModLegalityResponse(**result)