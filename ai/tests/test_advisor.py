"""Tests for the AI-gateway Ownership Advisor module (AUT-2450).

Mirrors the backend test in ``backend/tests/test_advisor_ai.py`` for the
two pieces that only live in the ``ai/`` package:

  * ``app.fallbacks.advisor.advisor_fallback`` (the rule tree)
  * ``app.fallbacks.advisor.validate_advisor_response`` (the response
    clamp that always returns a valid contract)

Plus an end-to-end test that the module is registered in
``app.modules.MODULES`` under the ``advisor`` key so the gateway
auto-discovers it.
"""

import os

os.environ.setdefault("AI_ROUTER_URL", "http://your-9router-instance:port")
os.environ.setdefault("AI_GATEWAY_API_KEY", "test-gateway-key")
os.environ.setdefault("AI_GATEWAY_AUTH_DISABLED", "1")

import pytest  # noqa: E402

from app.fallbacks.advisor import (  # noqa: E402
    advisor_fallback,
    validate_advisor_response,
)


# --- decision tree ---------------------------------------------------------


def test_advisor_fallback_upgrade_when_gap_small() -> None:
    modules = {
        "value": {"mid": 20_000.0},
        "replace": {"used_replacement_cost": 24_000.0, "funding_gap": 4_000.0},
        "upgrade": {},
        "finance": {},
        "dream": {},
    }
    out = advisor_fallback(modules)
    assert out["decision"] == "upgrade"
    assert out["model"] == "rule-based-fallback"


def test_advisor_fallback_delay_when_gap_huge() -> None:
    modules = {
        "value": {"mid": 20_000.0},
        "replace": {"used_replacement_cost": 50_000.0, "funding_gap": 30_000.0},
        "upgrade": {},
        "finance": {},
        "dream": {},
    }
    out = advisor_fallback(modules)
    assert out["decision"] == "delay"


def test_advisor_fallback_keep_when_gap_mid() -> None:
    modules = {
        "value": {"mid": 20_000.0},
        "replace": {"used_replacement_cost": 28_000.0, "funding_gap": 8_000.0},
        "upgrade": {},
        "finance": {},
        "dream": {},
    }
    out = advisor_fallback(modules)
    assert out["decision"] == "keep"


def test_advisor_fallback_strategy_when_dream_affordable() -> None:
    modules = {
        "value": {"mid": 20_000.0},
        "replace": {"used_replacement_cost": 30_000.0, "funding_gap": 10_000.0},
        "upgrade": {},
        "finance": {},
        "dream": {"affordability": "affordable"},
    }
    out = advisor_fallback(modules)
    assert out["decision"] == "strategy"


def test_advisor_fallback_handles_missing_keys() -> None:
    out = advisor_fallback({"value": {"mid": 1.0}})
    assert out["decision"] in ("keep", "delay")
    assert 0.0 <= out["confidence"] <= 1.0
    assert out["based_on"]["value"] is True
    for m in ("replace", "upgrade", "finance", "dream"):
        assert out["based_on"][m] is False


def test_advisor_fallback_handles_non_dict_payload() -> None:
    """Bad payload shapes never crash the gateway."""
    out = advisor_fallback(None)  # type: ignore[arg-type]
    assert out["decision"] == "keep"


def test_advisor_fallback_confidence_clamps_to_unit_interval() -> None:
    out = advisor_fallback({"value": {"mid": 1.0}})
    assert 0.0 <= out["confidence"] <= 1.0


# --- validate_advisor_response --------------------------------------------


def test_validate_clamps_unknown_decision_to_keep() -> None:
    out = validate_advisor_response({"decision": "sell-it", "confidence": 0.4})
    assert out["decision"] == "keep"


def test_validate_clamps_confidence_to_unit_interval() -> None:
    out = validate_advisor_response({"decision": "keep", "confidence": 5.0})
    assert out["confidence"] == 1.0
    out = validate_advisor_response({"decision": "keep", "confidence": -0.5})
    assert out["confidence"] == 0.0


def test_validate_clamps_rationale_to_280_chars() -> None:
    out = validate_advisor_response({"decision": "keep", "rationale": "x" * 1000})
    assert len(out["rationale"]) <= 280


def test_validate_limits_next_actions_to_3() -> None:
    out = validate_advisor_response({
        "decision": "keep",
        "next_actions": ["a", "b", "c", "d", "e"],
    })
    assert len(out["next_actions"]) == 3


def test_validate_drops_non_string_next_actions() -> None:
    out = validate_advisor_response({
        "decision": "keep",
        "next_actions": [None, 42, "real action", ""],
    })
    assert out["next_actions"] == ["real action"]


def test_validate_canonicalises_based_on_keys() -> None:
    out = validate_advisor_response({"decision": "keep", "based_on": {"value": 1, "hacker": True}})
    assert "hacker" not in out["based_on"]
    assert out["based_on"]["value"] is True


def test_validate_handles_empty_input() -> None:
    out = validate_advisor_response({})
    assert out["decision"] == "keep"
    assert 0.0 <= out["confidence"] <= 1.0
    assert out["model"] == "rule-based-fallback"


# --- module registration --------------------------------------------------


def test_advisor_module_registered_in_gateway() -> None:
    from app.modules import MODULES

    assert "advisor" in MODULES
    assert MODULES["advisor"] is not None
    assert callable(MODULES["advisor"])


@pytest.mark.asyncio
async def test_advisor_module_run_returns_validated_contract() -> None:
    """End-to-end: ``app.modules.advisor.run`` returns a valid contract
    even when 9Router is disabled (the default in this test env).
    """
    from app.modules import advisor as advisor_module

    payload = {
        "value": {"mid": 20_000.0},
        "replace": {"funding_gap": 4_000.0},
        "upgrade": {},
        "finance": {},
        "dream": {},
    }
    out = await advisor_module.run(payload)
    assert out["decision"] in ("keep", "upgrade", "delay", "strategy")
    assert 0.0 <= out["confidence"] <= 1.0
    assert isinstance(out["rationale"], str)
    assert len(out["rationale"]) <= 280
    assert isinstance(out["next_actions"], list)
    assert all(isinstance(a, str) for a in out["next_actions"])
    assert "model" in out


# --- router contract ------------------------------------------------------


def test_advisor_listed_in_system_prompts() -> None:
    from app.router_utils import _SYSTEM_PROMPTS

    assert "advisor" in _SYSTEM_PROMPTS
    assert "decision" in _SYSTEM_PROMPTS["advisor"]


def test_advisor_decision_marked_immutable() -> None:
    """The decision must be in the immutable set: the router cannot override it."""
    from app.router_utils import _AI_IMMUTABLE

    assert "advisor" in _AI_IMMUTABLE
    assert "decision" in _AI_IMMUTABLE["advisor"]


def test_advisor_schema_whitelisted() -> None:
    from app.router_utils import _SCHEMAS

    assert "advisor" in _SCHEMAS
    for key in ("decision", "confidence", "rationale", "next_actions", "based_on", "model"):
        assert key in _SCHEMAS["advisor"]
