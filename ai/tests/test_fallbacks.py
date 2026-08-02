"""Tests for rule-based fallback engines."""

import os

os.environ.setdefault("AI_ROUTER_URL", "http://your-9router-instance:port")

import pytest  # noqa: E402

from app import modules  # noqa: E402
from app.fallbacks import (  # noqa: E402
    diagnose_fallback,
    estimate_value_fallback,
    extract_receipt_fallback,
    mod_impact_fallback,
    predict_service_fallback,
)


def test_diagnostics_brake() -> None:
    out = diagnose_fallback("squealing brakes when stopping")
    assert out["severity"] == "high"
    assert out["items"][0]["confidence"] > 0.5
    assert out["model"] == "rule-based-fallback"


def test_diagnostics_obd() -> None:
    out = diagnose_fallback("engine running rough", obd_codes=["P0301"])
    assert any("misfire" in it["cause"].lower() for it in out["items"])


def test_service_prediction_oil() -> None:
    out = predict_service_fallback({"make": "Toyota", "odometer_km": 40000, "last_service_km": 35000,
                                    "service_type": "oil_change"})
    assert out["interval_km"] == 9000  # 10k * toyota 0.9
    assert out["next_due_km"] == 44000
    assert out["due_in_km"] == 4000


def test_resale_depreciation() -> None:
    out = estimate_value_fallback({
        "vehicle": {"make": "Toyota", "model": "Camry", "year": 2021,
                    "odometer_km": 30000, "condition": "good"},
        "service_count": 6,
    })
    assert 0 < out["low"] < out["estimated_value"] < out["high"]
    assert out["currency"] == "AUD"


def test_mod_impact() -> None:
    out = mod_impact_fallback({"name": "Cold air intake", "category": "performance", "cost": 400})
    assert out["performance_score"] >= 5
    assert out["value_impact"] > 0


def test_receipt_extraction() -> None:
    text = "SuperCheap Auto\nOil 35.00\nFilter 25.00\nLabour 90.00\nTotal 150.00"
    out = extract_receipt_fallback(text)
    assert out["vendor"] == "Supercheap"
    assert out["total"] == 150.0
    assert len(out["items"]) >= 2


@pytest.mark.asyncio
async def test_module_router_disabled_uses_fallback() -> None:
    out = await modules.diagnostics.run({"symptoms": "car won't start"})
    assert out["model"] == "rule-based-fallback"
