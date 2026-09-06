"""Tests for the AI-gateway Car Check module (AUT-2651).

Mirrors the backend test in ``backend/tests/test_car_check_ai.py`` for the
two pieces that only live in the ``ai/`` package:

  * ``app.fallbacks.car_check.car_check_fallback`` (the rule tree)
  * ``app.fallbacks.car_check.validate_car_check_response`` (the response
    clamp that always returns a valid contract)

Plus an end-to-end test that the module is registered in
``app.modules.MODULES`` under the ``car-check`` key so the gateway
auto-discovers it.
"""

import os

os.environ.setdefault("AI_ROUTER_URL", "http://your-9router-instance:port")
os.environ.setdefault("AI_GATEWAY_API_KEY", "test-gateway-key")
os.environ.setdefault("AI_GATEWAY_AUTH_DISABLED", "1")

import pytest  # noqa: E402

from app.fallbacks.car_check import (  # noqa: E402
    car_check_fallback,
    validate_car_check_response,
)


# --- fallback ---------------------------------------------------------------


def test_fallback_returns_contract() -> None:
    payload = {
        "deal_score": 72.5,
        "listing": {
            "title": "Honda CBR500R 2022",
            "price": 8_500.0,
            "year": 2022,
            "odometer_km": 12_000,
            "make": "Honda",
            "model": "CBR500R",
            "listing_url": "https://example.com/cbr",
        },
    }
    out = car_check_fallback(payload)
    assert "summary" in out
    assert "red_flags" in out
    assert "green_flags" in out
    assert out["deal_score"] == 72.5
    assert out["model"] == "rule-based-fallback"


def test_fallback_missing_listing() -> None:
    out = car_check_fallback({"deal_score": 50})
    assert "summary" in out
    assert isinstance(out["red_flags"], list)
    assert isinstance(out["green_flags"], list)


def test_fallback_empty_payload() -> None:
    out = car_check_fallback({})
    assert out["deal_score"] is None
    assert out["model"] == "rule-based-fallback"


def test_fallback_non_dict_payload() -> None:
    out = car_check_fallback(None)  # type: ignore[arg-type]
    assert out["model"] == "rule-based-fallback"


def test_fallback_low_score_adds_red_flag() -> None:
    payload = {"deal_score": 20, "listing": {"price": 20_000.0, "make": "Toyota", "model": "Corolla"}}
    out = car_check_fallback(payload)
    assert any("well below" in f.lower() for f in out["red_flags"])


def test_fallback_missing_price_adds_red_flag() -> None:
    out = car_check_fallback({"deal_score": 80, "listing": {"make": "Toyota", "model": "Corolla"}})
    assert any("no price" in f.lower() for f in out["red_flags"])


def test_fallback_high_score_adds_green_flag() -> None:
    payload = {"deal_score": 90, "listing": {"price": 10_000.0, "year": 2022, "make": "Honda", "model": "CBR500R"}}
    out = car_check_fallback(payload)
    assert any("strong" in f.lower() for f in out["green_flags"])


# --- validate_car_check_response --------------------------------------------


def test_validate_clamps_summary_to_280() -> None:
    out = validate_car_check_response({"summary": "x" * 500, "deal_score": 50.0})
    assert len(out["summary"]) <= 280


def test_validate_limits_flags_to_5() -> None:
    flags = [f"flag {i}" for i in range(10)]
    out = validate_car_check_response({
        "summary": "ok", "red_flags": flags, "green_flags": flags, "deal_score": 50.0,
    })
    assert len(out["red_flags"]) <= 5
    assert len(out["green_flags"]) <= 5


def test_validate_clamps_deal_score_to_0_100() -> None:
    out = validate_car_check_response({"summary": "ok", "deal_score": 200.0})
    assert out["deal_score"] == 100.0
    out2 = validate_car_check_response({"summary": "ok", "deal_score": -10.0})
    assert out2["deal_score"] == 0.0


def test_validate_handles_empty_input() -> None:
    out = validate_car_check_response({})
    assert out["model"] == "rule-based-fallback"


def test_validate_drops_non_string_flags() -> None:
    out = validate_car_check_response({
        "summary": "ok",
        "red_flags": [None, 42, "real", ""],
        "green_flags": ["good", 99],
        "deal_score": 50.0,
    })
    assert out["red_flags"] == ["real"]
    assert out["green_flags"] == ["good"]


# --- module registration ----------------------------------------------------


def test_car_check_module_registered_in_gateway() -> None:
    from app.modules import MODULES

    assert "car-check" in MODULES
    assert callable(MODULES["car-check"])


@pytest.mark.asyncio
async def test_car_check_module_run_returns_validated_contract() -> None:
    """End-to-end: ``app.modules.car_check.run`` returns a valid contract
    even when 9Router is disabled (the default in this test env).
    """
    from app.modules import car_check as car_check_module

    payload = {
        "deal_score": 65.0,
        "listing": {
            "title": "Honda CBR500R",
            "price": 8_500.0,
            "year": 2022,
            "odometer_km": 12_000,
            "make": "Honda",
            "model": "CBR500R",
            "listing_url": "https://example.com/cbr",
        },
    }
    out = await car_check_module.run(payload)
    assert "summary" in out
    assert isinstance(out["summary"], str)
    assert len(out["summary"]) <= 280
    assert isinstance(out["red_flags"], list)
    assert isinstance(out["green_flags"], list)
    assert "model" in out


# --- router contract --------------------------------------------------------


def test_car_check_listed_in_system_prompts() -> None:
    from app.router_utils import _SYSTEM_PROMPTS

    assert "car-check" in _SYSTEM_PROMPTS
    assert "deal score" in _SYSTEM_PROMPTS["car-check"]
    assert "Do NOT invent" in _SYSTEM_PROMPTS["car-check"]


def test_car_check_deal_score_marked_immutable() -> None:
    """The deal_score must be in the immutable set: the router cannot override it."""
    from app.router_utils import _AI_IMMUTABLE

    assert "car-check" in _AI_IMMUTABLE
    assert "deal_score" in _AI_IMMUTABLE["car-check"]


def test_car_check_schema_whitelisted() -> None:
    from app.router_utils import _SCHEMAS

    assert "car-check" in _SCHEMAS
    for key in ("summary", "red_flags", "green_flags"):
        assert key in _SCHEMAS["car-check"]
