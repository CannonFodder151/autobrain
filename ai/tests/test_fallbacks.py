"""Tests for rule-based fallback engines."""

import os

os.environ.setdefault("AI_ROUTER_URL", "http://your-9router-instance:port")

import pytest  # noqa: E402

from app import modules  # noqa: E402
from app.fallbacks import (  # noqa: E402
    diagnose_fallback,
    estimate_condition,
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

def test_resale_everest_anchored_on_rrp() -> None:
    # Regression for AUT-161: a 2025 Ford Everest was valued ~20k because the
    # model fell back to the ford make default. RRP anchor must keep it
    # realistic (RRP ~62k, ~57k used).
    out = estimate_value_fallback({
        "vehicle": {"make": "Ford", "model": "Everest Trend", "year": 2025,
                    "odometer_km": 5000, "condition": "good"},
    })
    assert out["factors"]["rrp"] == 62000.0
    assert out["estimated_value"] > 45000
    assert out["model"] == "rrp-depreciation"

def test_resale_everest_used_price_refinement() -> None:
    # AI-supplied current selling price (~57.8k) refines the estimate in-band.
    out = estimate_value_fallback({
        "vehicle": {"make": "Ford", "model": "Everest Trend", "year": 2025,
                    "odometer_km": 5000, "condition": "good"},
    }, used_price=57800.0)
    assert 40000 < out["estimated_value"] < 70000
    assert out["low"] <= out["estimated_value"] <= out["high"]

def test_resale_used_price_cannot_skew_estimate() -> None:
    # A wildly wrong used price is clamped to the deterministic band.
    det = estimate_value_fallback({
        "vehicle": {"make": "Ford", "model": "Everest Trend", "year": 2025,
                    "odometer_km": 5000, "condition": "good"},
    })["estimated_value"]
    out = estimate_value_fallback({
        "vehicle": {"make": "Ford", "model": "Everest Trend", "year": 2025,
                    "odometer_km": 5000, "condition": "good"},
    }, used_price=19973.0)
    assert 0.8 * det <= out["estimated_value"] <= 1.2 * det

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
        # Every module returns a deterministic baseline (rule-based or the
        # rrp-depreciation resale model) with the router disabled.
        assert out["model"].startswith("rule-based") or out["model"] == "rrp-depreciation", name


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


@pytest.mark.asyncio
async def test_resale_run_computes_fallback_once(monkeypatch) -> None:
    # AUT-210: the deterministic fallback must run exactly once, not once for
    # the AI baseline and again after rrp/used_price enrichment.
    from app.modules import resale as resale_mod

    calls: list = []
    real = resale_mod.estimate_value_fallback

    def counting(*args, **kwargs):
        result = real(*args, **kwargs)
        calls.append((args, kwargs, result))
        return result

    monkeypatch.setattr(resale_mod, "estimate_value_fallback", counting)
    monkeypatch.setattr(resale_mod, "enhance", _async_identity)  # router down

    out = await resale_mod.run({
        "vehicle": {"make": "Toyota", "model": "Camry", "year": 2021,
                    "odometer_km": 30000, "condition": "good"},
        "service_count": 3,
    })
    assert len(calls) == 1
    assert out["estimated_value"] == calls[0][2]["estimated_value"]
    assert out["model"].startswith("rule-based") or out["model"] == "rrp-depreciation"


@pytest.mark.asyncio
async def test_resale_run_enrichment_computes_once(monkeypatch) -> None:
    # With AI-supplied facts, the single compute receives the enriched values.
    from app.modules import resale as resale_mod

    calls: list = []
    real = resale_mod.estimate_value_fallback

    def counting(*args, **kwargs):
        result = real(*args, **kwargs)
        calls.append((args, kwargs, result))
        return result

    monkeypatch.setattr(resale_mod, "estimate_value_fallback", counting)

    async def fake_enhance(module, payload, baseline):
        return {"used_price": 9999.0, "recommendations": ["Sell now"], "trend": []}

    monkeypatch.setattr(resale_mod, "enhance", fake_enhance)

    out = await resale_mod.run({
        "vehicle": {"make": "Ford", "model": "Everest Trend", "year": 2025,
                    "odometer_km": 5000, "condition": "good"},
    })
    assert len(calls) == 1
    assert calls[0][1]["used_price"] == 9999.0
    assert out["recommendations"][0] == "Sell now"


@pytest.mark.asyncio
async def test_resale_run_market_data_computes_once(monkeypatch) -> None:
    # AUT-287: real market median is the used_price the single compute sees.
    from app.modules import resale as resale_mod

    calls: list = []
    real = resale_mod.estimate_value_fallback

    def counting(*args, **kwargs):
        result = real(*args, **kwargs)
        calls.append((args, kwargs, result))
        return result

    monkeypatch.setattr(resale_mod, "estimate_value_fallback", counting)
    monkeypatch.setattr(resale_mod, "enhance", _async_identity)

    out = await resale_mod.run({
        "vehicle": {"make": "Toyota", "model": "Crown", "year": 1997,
                    "odometer_km": 120000, "condition": "good"},
        "market": {"source": "carsguide", "sample_size": 6, "median_price": 15000.0},
    })
    assert len(calls) == 1
    assert calls[0][1]["used_price"] == 15000.0
    assert out["factors"]["market_median"] == 15000.0
    assert out["model"] == "market-anchored"


async def _async_identity(module, payload, baseline):
    return baseline


def test_resale_market_data_anchors_crown() -> None:
    # Regression for AUT-287: the deterministic model undervalues a Toyota
    # Crown (~8k via the make-default anchor). Real CarsGuide/CarSales listings
    # (median ~15k) must anchor the estimate instead.
    out = estimate_value_fallback({
        "vehicle": {"make": "Toyota", "model": "Crown", "year": 1997,
                    "odometer_km": 120000, "condition": "good"},
        "market": {"source": "carsguide", "sample_size": 6,
                   "median_price": 15000.0, "low_price": 12000.0, "high_price": 18000.0},
    })
    assert out["factors"]["market_median"] == 15000.0
    assert 10000 <= out["estimated_value"] <= 17000
    assert out["factors"]["market_sample"] == 6
    assert out["model"] == "market-anchored"


def test_resale_market_data_stable_across_calls() -> None:
    # Cached market data must produce the same number every call (no AI wobble).
    payload = {
        "vehicle": {"make": "Toyota", "model": "Crown", "year": 1997,
                    "odometer_km": 120000, "condition": "good"},
        "market": {"source": "carsales", "sample_size": 8, "median_price": 15100.0},
    }
    first = estimate_value_fallback(payload)["estimated_value"]
    second = estimate_value_fallback(payload)["estimated_value"]
    assert first == second


def test_resale_market_data_bad_median_floored() -> None:
    # An absurd median can't collapse the estimate below half the
    # deterministic model's own number.
    det = estimate_value_fallback({
        "vehicle": {"make": "Toyota", "model": "Crown", "year": 1997,
                    "odometer_km": 120000, "condition": "good"},
    })["estimated_value"]
    out = estimate_value_fallback({
        "vehicle": {"make": "Toyota", "model": "Crown", "year": 1997,
                    "odometer_km": 120000, "condition": "good"},
        "market": {"source": "carsguide", "sample_size": 10, "median_price": 100.0},
    })
    assert out["estimated_value"] >= 0.5 * det


def test_resale_market_data_tiny_sample_ignored() -> None:
    # <3 listings is not a reliable market — fall back to the AI used_price band.
    det = estimate_value_fallback({
        "vehicle": {"make": "Ford", "model": "Everest Trend", "year": 2025,
                    "odometer_km": 5000, "condition": "good"},
    })["estimated_value"]
    out = estimate_value_fallback({
        "vehicle": {"make": "Ford", "model": "Everest Trend", "year": 2025,
                    "odometer_km": 5000, "condition": "good"},
        "market": {"source": "carsales", "sample_size": 2, "median_price": 300000.0},
    }, used_price=57800.0)
    assert 0.8 * det <= out["estimated_value"] <= 1.2 * det


def test_condition_clean_well_serviced() -> None:
    out = estimate_condition({
        "vehicle": {"make": "Toyota", "odometer_km": 40000, "year": 2020},
        "service_count": 6,
        "total_service_cost": 4000.0,
        "last_service_days_ago": 60,
        "diagnostics": [],
    })
    assert out["condition"] in ("excellent", "good")
    assert out["confidence"] > 0.7


def test_condition_open_critical_issue_poor() -> None:
    out = estimate_condition({
        "vehicle": {"make": "Yamaha", "odometer_km": 30000, "year": 2018, "vehicle_type": "motorcycle"},
        "diagnostics": [{"severity": "critical", "status": "open"}],
        "service_count": 0,
        "last_service_days_ago": None,
    })
    assert out["condition"] == "poor"
    assert any("open issue" in s for s in out["factors"]["signals"])
    assert "critical fault present" in out["factors"]["signals"]


def test_condition_bike_km_scale_differs() -> None:
    # 30k km on a 4-yr-old bike = high vs expected (~24k) but not crazy for a
    # car — the motorcycle km/year scale must apply.
    car = estimate_condition({
        "vehicle": {"make": "Honda", "odometer_km": 30000, "year": 2022, "vehicle_type": "car"},
        "service_count": 4, "last_service_days_ago": 100,
    })
    bike = estimate_condition({
        "vehicle": {"make": "Honda", "odometer_km": 30000, "year": 2022, "vehicle_type": "motorcycle"},
        "service_count": 4, "last_service_days_ago": 100,
    })
    assert car["score"] > bike["score"]


def test_condition_user_override_not_overwritten_by_resale() -> None:
    # When the user supplies a condition, resale keeps it (no estimate step).
    out = estimate_value_fallback({
        "vehicle": {"make": "Toyota", "model": "Crown", "year": 1997,
                    "odometer_km": 120000, "condition": "excellent"},
        "diagnostics": [{"severity": "critical", "status": "open"}],
    })
    assert out["factors"]["condition"] == "excellent"
    assert "condition_estimate" not in out["factors"]
