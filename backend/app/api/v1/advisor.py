"""Ownership Advisor API surface (AUT-2425, AUT-2445-VALUE, AUT-2448-FINANCE,
AUT-2449-DREAM, AUT-2450-AI).

Frozen route layout per ADR 0001
(``docs/adr/0001-ownership-advisor.md``):

- ``GET  /api/v1/advisor/value``   — AUT-2445 (this module)
- ``GET  /api/v1/advisor/replace`` — AUT-2446
- ``GET  /api/v1/advisor/upgrade`` — AUT-2447
- ``POST /api/v1/advisor/finance`` — AUT-2448 (this module)
- ``POST /api/v1/advisor/dream``   — AUT-2449 (this module)
- ``POST /api/v1/advisor/ai``      — AUT-2450 (only module that hits 9Router)

This router file ships the ``value`` + ``finance`` + ``dream`` + ``ai``
sub-modules. Other sub-modules land in their own PRs so they can ship
in parallel behind the frozen envelope.

Value is deterministic: it anchors on the cached market median
(``app.services.market_data``), applies a condition multiplier + km
adjustment, surfaces a low / mid / high band, and lists comparables
(same make/model, year ±3) from the same cache. Trade-in band is the
industry-standard 75 / 82 / 90% of mid private-sale value.

Finance (AUT-2448) is also fully deterministic: pure-function amortisation
on top of the value module's mid price. No 9Router call. The novated-lease
block is future-flagged (``status="coming_soon"``) until the EV / FBT
rules land in a follow-up ADR.

Dream Car (AUT-2449) is the only POST module that doesn't anchor on
the user's current vehicle. It looks up an arbitrary (make, model,
year) on ``market_listing_cache`` (same key shape, no duplicate
storage), computes an indicative monthly repayment via the same
``_loan_monthly_payment`` helper the Finance module publishes, and —
when the user supplies a finance profile in the request body — surfaces
an affordability gap (cash shortfall + DSR ceiling check).

AI Advisor (AUT-2450) is the only module that hits 9Router. It consumes
structured outputs from the Value/Replace/Upgrade/Finance/Dream sub-modules
and returns ``{decision, confidence, rationale, next_actions, based_on}``.
The decision is deterministic (rule tree); 9Router enriches rationale +
next_actions but cannot change the decision. When the AI gateway is
unreachable the route falls back to ``app.services.advisor.compute_advisor_recommendation``
(same rule tree) so the user always gets an answer; ``model`` is then
``rule-based-fallback``. 24h in-process LRU+TTL cache keyed by
``sha256(sorted_module_outputs)`` in ``app.services.ai_client``.

Entitlement: free accounts get ``403``; demo accounts are allowed (value
+ finance + dream are deterministic, no AI; AI Advisor is paid-only).
Sharing rules reuse the existing ``get_accessible_vehicle`` helper from
``app.services.ownership`` (Dream doesn't need it — no current vehicle
in scope).
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
    AdvisorDreamData,
    AdvisorDreamRequest,
    AdvisorReplaceData,
    FundingGapBand,
    AdvisorFinanceData,
    AdvisorFinanceRequest,
    AdvisorResponse,
    AdvisorUpgradeData,
    UpgradeOption,
    SimilarVehicleSuggestion,
    TradeUpDelta,
    AdvisorValueData,
    ComparableListing,
    TradeInBand,
)
from app.services.advisor import (
    compute_advisor_recommendation,
    compute_dream,
    compute_finance_plan,
    compute_market_value,
    compute_upgrade,
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


@router.get("/replace", response_model=AdvisorResponse)
async def advisor_replace(
    vehicle_id: str = Query(..., description="Vehicle UUID (owner or accepted share)"),
    odometer_km: int | None = Query(None, ge=0, description="Optional override of the vehicle's stored odometer"),
    horizon_months: int | None = Query(
        None,
        ge=1,
        le=240,
        description="Saving horizon for the monthly target (default 36). Server clamps to [6, 120].",
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdvisorResponse:
    """Replacement cost (used + new) + funding gap + monthly saving target.

    Deterministic only — no 9Router. Reuses the value module's cached
    market median and the documented new-vs-used premium curve (see
    ``app.services.advisor.new_used_premium``). Funding gap follows the
    AC literally::

        gap = replacement_cost - current_value - trade_in_mid

    where ``trade_in_mid`` is the industry-standard 82% of private-sale
    mid surfaced by ``trade_in_band``. ``monthly_target = gap /
    horizon_months``; a negative gap (cheaper to replace than your
    current car + trade-in is worth) is surfaced as ``surplus=True``
    with a zero monthly target.

    No market data → all gap fields null, ``note`` explains why (same
    graceful fallback the value module uses).
    """
    _enforce_entitlement(user)
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)

    plan = await compute_replace(
        db, vehicle, odometer_km=odometer_km, horizon_months=horizon_months,
    )
    plan["trade_in"] = TradeInBand(**plan["trade_in"])
    plan["funding_gap"] = FundingGapBand(**plan["funding_gap"])
    data = AdvisorReplaceData(**plan)

    factors = {
        "vehicle": {
            "id": vehicle.id,
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
            "odometer_km": odometer_km if odometer_km is not None else vehicle.odometer_km,
            "vehicle_type": vehicle.vehicle_type,
        },
        "age_years": data.age_years,
        "new_used_premium": data.new_used_premium,
        "horizon_months": data.horizon_months,
    }

    return AdvisorResponse(
        module="replace",
        vehicle_id=vehicle.id,
        generated_at=datetime.now(timezone.utc),
        model="rule-based-fallback",
        data=data.model_dump(),
        factors=factors,
    )

@router.get("/upgrade", response_model=AdvisorResponse)
async def advisor_upgrade(
    vehicle_id: str = Query(..., description="Vehicle UUID (owner or accepted share)"),
    max_monthly: float | None = Query(None, ge=0, description="Optional cap on monthly repayment"),
    min_similarity: float | None = Query(None, ge=0, le=1, description="Minimum similarity score (0-1)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdvisorResponse:
    """Ranked upgrade candidates + trade-up estimate (AUT-2447).

    Deterministic only — no 9Router. Anchors on the value module's cached
    market median for the current vehicle, walks one or two tiers up
    (higher-trim or one model-year newer), ranks by similarity score, and
    attaches a built-in monthly finance estimate using the same amortisation
    helper the Finance module uses. Free accounts get 403.
    """
    _enforce_entitlement(user)
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)

    plan = await compute_upgrade(db, vehicle)

    # Filter upgrade options by optional similarity score.
    options = plan.get("upgrade_options", [])
    if min_similarity is not None:
        options = [c for c in options if c.get("score", 0.0) >= min_similarity]

    # Filter trade-up rows by optional monthly cap.
    trade_up = plan.get("trade_up", [])
    if max_monthly is not None:
        allowed_years = {
            (t.get("upgrade_year"), t.get("tier_label"))
            for t in trade_up
            if t.get("monthly_repayment") is not None and t.get("monthly_repayment") <= max_monthly
        }
        options = [
            o for o in options
            if (o.get("year"), o.get("tier_label")) in allowed_years
        ]

    plan["upgrade_options"] = options
    data = AdvisorUpgradeData(**plan)

    factors = {
        "vehicle": {
            "id": vehicle.id,
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
            "condition": vehicle.condition,
            "odometer_km": vehicle.odometer_km,
            "vehicle_type": vehicle.vehicle_type,
        },
        "filters": {
            "max_monthly": max_monthly,
            "min_similarity": min_similarity,
        },
        "candidate_count": len(data.upgrade_options),
    }

    return AdvisorResponse(
        module="upgrade",
        vehicle_id=vehicle.id,
        generated_at=datetime.now(timezone.utc),
        model="rule-based-fallback",
        data=data.model_dump(),
        factors=factors,
    )

@router.post("/finance", response_model=AdvisorResponse)
async def advisor_finance(
    payload: AdvisorFinanceRequest,
    vehicle_id: str = Query(..., description="Vehicle UUID (owner or accepted share)"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdvisorResponse:
    """Buy / finance / lease (and novated toggle, future-flagged) plan.

    Deterministic only. ``vehicle_price`` is anchored on the value
    module's ``mid`` (cached market median × condition × km adjustment),
    so the finance block never invents a price and the value + finance
    modules stay internally consistent. Falls back to ``0.0`` for
    ``vehicle_price`` when the value module has no market data — the
    response then carries a ``note`` explaining the gap so the UI can
    render a graceful empty state instead of fabricating numbers.
    """
    _enforce_entitlement(user)
    vehicle = await get_accessible_vehicle(db, vehicle_id, user)

    value = await compute_market_value(db, vehicle)
    vehicle_price = float(value.get("mid") or 0.0)

    plan = compute_finance_plan(
        vehicle_price=vehicle_price,
        down_payment=payload.down_payment,
        term_months=payload.term_months,
        rate_pct=payload.rate_pct,
        novated=payload.novated,
    )
    plan["vehicle_price"] = vehicle_price

    data = AdvisorFinanceData(**plan)
    factors = {
        "vehicle": {
            "id": vehicle.id,
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
            "condition": vehicle.condition,
            "vehicle_type": vehicle.vehicle_type,
        },
        "input": {
            "down_payment": payload.down_payment,
            "term_months": data.modes[1]["term_months"] if len(data.modes) > 1 else payload.term_months,
            "rate_pct": payload.rate_pct,
            "novated": payload.novated,
        },
        "anchored_value": {
            "mid": value.get("mid"),
            "source": value.get("source"),
            "as_of": value.get("as_of"),
            "stale": value.get("stale"),
        },
    }

    return AdvisorResponse(
        module="finance",
        vehicle_id=vehicle.id,
        generated_at=datetime.now(timezone.utc),
        model="rule-based-fallback",
        data=data.model_dump(),
        factors=factors,
    )


@router.post("/dream", response_model=AdvisorResponse)
async def advisor_dream(
    payload: AdvisorDreamRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AdvisorResponse:
    """Dream Car plan: lookup + affordability + indicative repayments.

    Deterministic only — no 9Router. Three blocks:

    - ``data.target``: market-data lookup for (make, model, year) via
      ``app.services.market_data.get_market_data``. Reuses the existing
      ``market_listing_cache`` row (same key shape as Value — no
      duplicate storage, ADR 0001 §2.5).
    - ``data.affordability``: pure arithmetic on the optional request
      body fields ``annual_income`` / ``monthly_expenses`` /
      ``cash_on_hand``. Surplus flag fires when the user can fund the
      deposit AND keep the indicative monthly under the 30% DSR ceiling
      on disposable income.
    - ``data.repayments``: wraps the existing ``_loan_monthly_payment``
      helper (same one the Finance module publishes) so consecutive
      calls return the same numbers for the same inputs.

    The Dream Car lookup is not tied to the user's current vehicle —
    ``vehicle_id`` in the envelope is left ``None``. When the cache has
    no row for the target, the response still ships a well-formed
    envelope with ``data.target.mid = null`` and a ``note`` explaining
    the gap, mirroring Value/Finance's "no market data" graceful
    fallback. Free accounts get 403.
    """
    _enforce_entitlement(user)

    plan = await compute_dream(
        db,
        make=payload.make,
        model=payload.model,
        year=payload.year,
        vehicle_type=payload.vehicle_type,
        finance_term_months=payload.finance_term_months,
        rate_pct=payload.rate_pct,
        deposit_pct=payload.deposit_pct,
        annual_income=payload.annual_income,
        monthly_expenses=payload.monthly_expenses,
        cash_on_hand=payload.cash_on_hand,
    )
    data = AdvisorDreamData(**plan)

    factors = {
        "target": {
            "make": data.target.make,
            "model": data.target.model,
            "year": data.target.year,
            "vehicle_type": data.target.vehicle_type,
        },
        "finance_term_months": data.repayments.finance_term_months,
        "rate_pct": data.repayments.rate_pct,
        "deposit_pct": data.repayments.deposit_pct,
        "dsr_ceiling": 0.30,
        "profile_provided": (
            payload.annual_income is not None
            and payload.monthly_expenses is not None
        ),
    }

    return AdvisorResponse(
        module="dream",
        vehicle_id=None,
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
        model=model,
        data=data.model_dump(),
        factors=factors,
    )
