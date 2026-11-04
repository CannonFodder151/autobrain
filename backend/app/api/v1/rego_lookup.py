"""Rego (Australian registration plate) lookup endpoint.

GET /api/v1/rego/lookup?rego=...&state=VIC

The heavy lifting lives in ``app.services.rego`` which returns a plain dict
with a deterministic fallback so the feature works end-to-end offline.
"""

from fastapi import APIRouter, Query

from app.services.rego import lookup_rego

router = APIRouter(prefix="/rego", tags=["rego"])

@router.get("/lookup")
async def rego_lookup(
    rego: str = Query(..., description="Australian registration plate"),
    state: str = Query("NSW", description="Australian state code"),
):
    info = await lookup_rego(rego, state=state)
    if info is None:
        return {
            "rego": rego,
            "state": state,
            "vin": None,
            "body": None,
            "colour": None,
            "status": "unknown",
            "make": None,
            "model": None,
            "year": None,
            "errors": ["invalid plate format"],
        }
    return info
