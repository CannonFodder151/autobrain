"""Ownership Advisor API surface (AUT-2425, AUT-2445-VALUE).

Frozen route layout per ADR 0001
(``docs/adr/0001-ownership-advisor.md``):

- ``GET  /api/v1/advisor/value``   — AUT-2445 (this module)
- ``GET  /api/v1/advisor/replace`` — AUT-2446
- ``GET  /api/v1/advisor/upgrade`` — AUT-2447
- ``POST /api/v1/advisor/finance`` — AUT-2448
- ``POST /api/v1/advisor/dream``   — AUT-2449
- ``POST /api/v1/advisor/ai``      — AUT-2450 (only module that hits 9Router)

This router file ships the ``value`` sub-module only. Other sub-modules
land in their own PRs so they can ship in parallel behind the frozen
envelope.

Value is deterministic: it anchors on the cached market median
(``app.services.market_data``), applies a condition multiplier + km
adjustment, surfaces a low / mid / high band, and lists comparables
(same make/model, year ±3) from the same cache. Trade-in band is the
industry-standard 75 / 82 / 90% of mid private-sale value.

The AI Advisor route (``POST /advisor/ai``) is shipped in the same
file because it shares entitlement + the universal response envelope
(``AdvisorResponse``). It is the only advisor module that hits 9Router;
when the gateway is unreachable it falls back to the same deterministic
rule tree (mirrored in ``app.services.advisor.compute_advisor_recommendation``).

Entitlement: free accounts get ``403``; demo accounts are allowed (value
is deterministic, no AI). Sharing rules reuse the existing
``get_accessible_vehicle`` helper from ``app.services.ownership``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.advisor import (
    AdvisorAIData,
    AdvisorAIRequest,
    AdvisorResponse,
    AdvisorValueData,
    ComparableListing,
    TradeInBand,
)
from app.services.advisor import (
    compute_advisor_recommendation,
    compute_market_value,
    find_comparables,
    trade_in_band,
)
from app.services.ai_client import run_advisor_ai
from app.services.ownership import get_accessible_vehicle

router = APIRouter(prefix="/advisor", tags=["advisor"])


def _enforce_entitlement(user: User) -> None:
    """Free accounts (admin-managed) get 403 on every advisor module.

    Demo accounts are read-only and may use deterministic modules; only
    the AI Advisor (separate module, AUT-2450) blocks them.
    """
    if user.free_account:
        raise HTTPException(
            status_code=403,
            detail="Ownership Advisor is a paid feature. Upgrade to enable it.",
        )


@router.get("/value", response_model=AdvisorResponse)
async def advisor_value(
    vehicle_id: str = Query(..., description="Vehicle UUID (owner or accepted share)"),
    odometer_km: int | None = Query(None, ge=0, description="Optional override of the vehicle's stored odometer"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdvisorResponse:
    """Current vehicle market value + comparables + trade-in band.

    Deterministic. Reuses the existing ``market_listing_cache`` (24h TTL)
    via ``app.services.market_data.get_market_data``; no 9Router / no AI
    gateway call. When the cache has no data for the vehicle, the response
    still returns a well-formed envelope with ``data.mid = null`` and a
    ``note`` explaining the gap, so the frontend can render a graceful
    "no market data" state.
    """
    _enforce_entitlement(user)
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)

    value = await compute_market_value(db, vehicle, odometer_km=odometer_km)
    comparables_raw = await find_comparables(db, vehicle)
    value["comparable_count"] = len(comparables_raw)
    value["comparables"] = [
        ComparableListing(**c) for c in comparables_raw
    ]
    value["trade_in"] = TradeInBand(**trade_in_band(value.get("mid")))

    data = AdvisorValueData(**value)
    factors = {
        "vehicle": {
            "id": vehicle.id,
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
            "condition": vehicle.condition,
            "odometer_km": odometer_km if odometer_km is not None else vehicle.odometer_km,
            "vehicle_type": vehicle.vehicle_type,
        },
        "condition_multiplier": data.condition_multiplier,
        "km_multiplier": data.km_multiplier,
        "comparable_window_years": data.comparable_window_years,
    }

    return AdvisorResponse(
        module="value",
        vehicle_id=vehicle.id,
        generated_at=datetime.now(timezone.utc),
        model="rule-based-fallback",
        data=data.model_dump(),
        factors=factors,
    )


@router.post("/ai", response_model=AdvisorResponse)
async def advisor_ai(
    body: AdvisorAIRequest,
    vehicle_id: str = Query(..., description="Vehicle UUID (owner or accepted share)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdvisorResponse:
    """AI-owned decision over Value/Replace/Upgrade/Finance/Dream (AUT-2450).

    Body: ``AdvisorAIRequest`` — the caller's already-fetched structured
    outputs from the other sub-modules. The AI never re-fetches them and
    never invents numbers; it only reasons over what was supplied.

    Returns the same ``AdvisorResponse`` envelope as the deterministic
    modules so the frontend can render any module with one parser.

    Routing: 9Router via the AI gateway (``ai/app/modules/advisor.py``).
    The gateway's deterministic baseline (``ai/app/fallbacks/advisor.py``)
    runs first; the router may add a richer rationale and sharper
    ``next_actions`` but the decision is the rule-tree's and cannot be
    overridden. When the gateway is unreachable the route falls back to
    ``app.services.advisor.compute_advisor_recommendation`` (same rule
    tree) so the user always gets an answer; ``model`` is then
    ``rule-based-fallback``.

    Caching: 24h, keyed by ``(vehicle_id, sha256(sorted_module_outputs))``
    in an in-process LRU+TTL in ``app.services.ai_client``. The cache
    is per-process; restart-eviction is acceptable because the cache
    only optimises repeat calls, not correctness.
    """
    _enforce_entitlement(user)
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)

    modules = {
        "value": body.value,
        "replace": body.replace,
        "upgrade": body.upgrade,
        "finance": body.finance,
        "dream": body.dream,
        "question": body.question,
    }

    ai_result = await run_advisor_ai(vehicle.id, modules)
    if ai_result:
        data = AdvisorAIData(
            decision=ai_result.get("decision", "keep"),
            confidence=ai_result.get("confidence", 0.5),
            rationale=ai_result.get("rationale", ""),
            next_actions=list(ai_result.get("next_actions") or []),
            based_on=ai_result.get("based_on") or {},
        )
        model = ai_result.get("model") or "9router/<combo>"
        factors = {
            "vehicle": {
                "id": vehicle.id,
                "make": vehicle.make,
                "model": vehicle.model,
                "year": vehicle.year,
            },
            "router_provenance": model,
            "cache_hit": False,
        }
    else:
        baseline = await compute_advisor_recommendation(modules)
        data = AdvisorAIData(
            decision=baseline["decision"],
            confidence=baseline["confidence"],
            rationale=baseline["rationale"],
            next_actions=baseline["next_actions"],
            based_on=baseline["based_on"],
        )
        model = "rule-based-fallback"
        factors = {
            "vehicle": {
                "id": vehicle.id,
                "make": vehicle.make,
                "model": vehicle.model,
                "year": vehicle.year,
            },
            "router_provenance": None,
            "fallback_reason": "ai_gateway_unreachable",
        }

    return AdvisorResponse(
        module="ai",
        vehicle_id=vehicle.id,
        generated_at=datetime.now(timezone.utc),
        model=model,  # type: ignore[arg-type]
        data=data.model_dump(),
        factors=factors,
    )
