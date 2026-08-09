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


def test_diagnostics_multiple_rules() -> None:
    out = diagnose_fallback("squealing brakes and the car vibrates at speed")
    causes = [it["cause"].lower() for it in out["items"]]
    assert any("brake" in c for c in causes)
    assert any("vibration" in c for c in causes)


def test_diagnostics_symptom_parts() -> None:
    out = diagnose_fallback("misfire when cold")
    parts = " ".join(out["parts_needed"]).lower()
    assert "spark plug" in parts and "ignition coil" in parts


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


def test_resale_crown_victoria_holds_value() -> None:
    # Regression for AUT-146: an old Crown Vic must not decay to ~$2k.
    out = estimate_value_fallback({
        "vehicle": {"make": "Ford", "model": "Crown Victoria", "year": 2008,
                    "odometer_km": 180000, "condition": "good"},
        "service_count": 3,
    })
    assert out["estimated_value"] >= 10000
    assert out["confidence"] >= 0.9


def test_resale_unknown_model_sane_floor() -> None:
    out = estimate_value_fallback({
        "vehicle": {"make": "Ford", "model": "Crown Victoria", "year": 2000,
                    "odometer_km": 250000, "condition": "fair"},
    })
    # 24-year-old car still holds a floor; never collapses to the old ~$2k.
    assert out["estimated_value"] >= 8000


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
    # Force the router-disabled path regardless of the container env,
    # so the test never calls a live router and never burns API quota.
    os.environ["AI_ROUTER_URL"] = "http://your-9router-instance:port"
    out = await modules.diagnostics.run({"symptoms": "car won't start"})
    assert out["model"] == "rule-based-fallback"


@pytest.mark.asyncio
async def test_module_deterministic_model_label() -> None:
    # Deterministic-first: every module returns a rule-based baseline (with the
    # router disabled), never an AI-only response.
    os.environ["AI_ROUTER_URL"] = "http://your-9router-instance:port"
    cases = [
        ("diagnostics", {"symptoms": "squealing brakes"}),
        ("service-prediction", {"make": "Toyota", "odometer_km": 40000, "last_service_km": 35000}),
        ("ocr", {"content": "SuperCheap Auto\nOil 35.00\nFilter 25.00\nTotal 60.00"}),
        ("fuel-ocr", {"content": "Shell\n45.20L @ 2.09\nTotal 94.47"}),
        ("odometer", {"content": "odometer 123456 km"}),
        ("resale", {"vehicle": {"make": "Toyota", "model": "Camry", "year": 2021}}),
        ("mod-impact", {"name": "Cold air intake", "category": "performance"}),
    ]
    for name, payload in cases:
        out = await modules.MODULES[name](payload)
        assert out["model"].startswith("rule-based"), name


def test_fuel_receipt_fallback() -> None:
    from app.modules.fuel_ocr import _fuel_receipt_fallback

    out = _fuel_receipt_fallback("Shell\n98 Premium\n45.20L @ 2.09\nTotal 94.47")
    assert out["litres"] == 45.2
    assert out["price_per_litre"] == 2.09
    assert out["total_cost"] == 94.47
    assert out["vendor"] == "Shell"


def test_odometer_fallback() -> None:
    from app.modules.odometer import _odometer_fallback, _clamp

    out = _odometer_fallback("odometer 123456 km")
    assert out["odometer_km"] == 123456
    clamped = _clamp({"odometer_km": "88000", "confidence": 0.9})
    assert clamped["odometer_km"] == 88000
    assert clamped["confidence"] == 0.9


def test_resale_validate_clamps() -> None:
    from app.modules.resale import _validate

    out = _validate({"estimated_value": 30000, "low": 50000, "high": 60000, "currency": "AUD"})
    assert out["low"] <= out["estimated_value"] <= out["high"]
    assert out["low"] == 27000.0  # 10% below the estimate when the range is invalid
    assert out["currency"] == "AUD"
