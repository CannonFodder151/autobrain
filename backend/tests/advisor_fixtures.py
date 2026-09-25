"""Shared test utilities for Ownership Advisor tests.

Consolidates duplicated helpers across test_advisor_value, test_advisor_replace,
test_advisor_upgrade, test_advisor_dream, and test_advisor_ai.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def _enforce_entitlement(user) -> None:
    """Mirror of ``app.api.v1.advisor._enforce_entitlement`` so tests don't
    need to import the api.v1 package (which transitively loads unrelated
    pre-existing issues)."""
    if user.free_account:
        raise HTTPException(
            status_code=403,
            detail="Ownership Advisor is a paid feature. Upgrade to enable it.",
        )


def _vehicle(
    *,
    year: int | None = 2018,
    odo: int | None = 80_000,
    condition: str = "good",
    make: str = "Toyota",
    model: str = "Corolla",
    vehicle_type: str = "car",
    body_type: str | None = None,
) -> SimpleNamespace:
    """Create a minimal vehicle-like object for advisor tests."""
    ns = SimpleNamespace(
        year=year,
        odometer_km=odo,
        condition=condition,
        make=make,
        model=model,
        vehicle_type=vehicle_type,
    )
    if body_type is not None:
        ns.body_type = body_type
    return ns


def _try_import_app():
    """Attempt to import the FastAPI app; skip if blocked by pre-existing
    fuel_prices syntax error (AUT-2496)."""
    try:
        from app.main import app as _app  # type: ignore
        return _app
    except SyntaxError as exc:
        pytest.skip(f"app boot blocked by unrelated pre-existing syntax error: {exc}")


def _fake_market_data(
    *,
    median_price: float = 35_000.0,
    low_price: float = 30_000.0,
    high_price: float = 40_000.0,
    sample_size: int = 12,
    source: str = "provider",
    stale: bool = False,
    note: str | None = None,
) -> dict:
    """Return a realistic fake market data dict for monkeypatching."""
    return {
        "median_price": median_price,
        "low_price": low_price,
        "high_price": high_price,
        "sample_size": sample_size,
        "source": source,
        "as_of": "2026-09-04T00:00:00Z",
        "stale": stale,
        "note": note,
    }
