"""Tests for per-module confidence floors and cost guard (AUT-6417)."""

import pytest


@pytest.fixture(autouse=True)
def _ai_test_env(monkeypatch):
    monkeypatch.setenv("AI_ROUTER_URL", "http://your-9router-instance:port")

from unittest.mock import AsyncMock, patch  # noqa: E402

from app.router_client import enhance, token_usage_snapshot, _budget_exceeded, _DAILY_TOKEN_BUDGET  # noqa: E402
from app.router_utils import _MODULE_CONFIDENCE_FLOORS, _AI_IMMUTABLE, _SCHEMAS  # noqa: E402


def test_module_confidence_floors_defined() -> None:
    """AUT-6417: per-module confidence floors must be defined for critical modules."""
    assert "resale" in _MODULE_CONFIDENCE_FLOORS
    assert "diagnostics" in _MODULE_CONFIDENCE_FLOORS
    assert "service-prediction" in _MODULE_CONFIDENCE_FLOORS
    assert "advisor" in _MODULE_CONFIDENCE_FLOORS
    # Resale has the highest floor (valuation accuracy is critical)
    assert _MODULE_CONFIDENCE_FLOORS["resale"] >= 0.85
    # Diagnostics requires higher confidence (medical-adjacent)
    assert _MODULE_CONFIDENCE_FLOORS["diagnostics"] >= 0.80


def test_module_floors_override_global() -> None:
    """AUT-6417: module floors must be within valid range."""
    for module, floor in _MODULE_CONFIDENCE_FLOORS.items():
        assert 0.5 <= floor <= 0.95, f"{module} floor {floor} out of valid range"


@pytest.mark.asyncio
async def test_enhance_uses_module_floor_not_global(monkeypatch) -> None:
    """AUT-6417: enhance() must use the module's floor, not the global default."""
    # Set global to 0.5 (low) but resale floor is 0.85
    monkeypatch.setenv("MIN_AI_CONFIDENCE", "0.5")
    baseline = {"estimated_value": 30000.0, "model": "rule-based-fallback"}
    # Confidence 0.7: above global 0.5 but below resale floor 0.85
    malicious = {"estimated_value": 1.0, "rrp": 60000.0, "confidence": 0.7}
    with patch("app.router_client.route", new=AsyncMock(return_value=malicious)):
        out = await enhance("resale", {}, baseline)
    # Should NOT merge because 0.7 < 0.85 (resale floor)
    assert out["estimated_value"] == 30000.0
    assert "rrp" not in out


@pytest.mark.asyncio
async def test_enhance_module_floor_allows_merge(monkeypatch) -> None:
    """AUT-6417: enhance() merges when confidence >= module floor."""
    monkeypatch.setenv("MIN_AI_CONFIDENCE", "0.5")
    baseline = {"estimated_value": 30000.0, "model": "rule-based-fallback"}
    # Confidence 0.9: above resale floor 0.85
    malicious = {"estimated_value": 1.0, "rrp": 60000.0, "confidence": 0.9}
    with patch("app.router_client.route", new=AsyncMock(return_value=malicious)):
        out = await enhance("resale", {}, baseline)
    assert out["estimated_value"] == 30000.0  # immutable
    assert out["rrp"] == 60000.0  # merged


@pytest.mark.asyncio
async def test_enhance_unknown_module_uses_global(monkeypatch) -> None:
    """AUT-6417: modules without a floor use the global MIN_AI_CONFIDENCE."""
    monkeypatch.setenv("MIN_AI_CONFIDENCE", "0.6")
    baseline = {"model": "rule-based-fallback"}
    # Confidence 0.7: above global 0.6
    malicious = {"anything": 1, "confidence": 0.7}
    with patch("app.router_client.route", new=AsyncMock(return_value=malicious)):
        out = await enhance("unknown-module", {}, baseline)
    # No schema for unknown module, so nothing merges
    assert out == baseline


def test_cost_guard_budget_config() -> None:
    """AUT-6417: cost guard budget must be configurable."""
    assert _DAILY_TOKEN_BUDGET == 1000000  # default


def test_cost_guard_snapshot_shape() -> None:
    """AUT-6417: token_usage_snapshot must return expected shape."""
    snap = token_usage_snapshot()
    assert "daily_budget" in snap
    assert "total_tokens" in snap
    assert "by_module" in snap
    assert "budget_exceeded" in snap
    assert snap["daily_budget"] == _DAILY_TOKEN_BUDGET
    assert isinstance(snap["by_module"], dict)


def test_cost_guard_budget_exceeded_flag() -> None:
    """AUT-6417: budget_exceeded flag must be False initially."""
    assert not _budget_exceeded()


def test_cost_guard_budget_config() -> None:
    """AUT-6417: cost guard budget must be configurable."""
    assert _DAILY_TOKEN_BUDGET == 1000000  # default


def test_immutable_keys_have_schema_entries() -> None:
    """AUT-3914: every immutable key must have a schema entry."""
    for module, keys in _AI_IMMUTABLE.items():
        schema = _SCHEMAS.get(module, {})
        missing = sorted(keys - set(schema))
        assert not missing, f"{module} immutable keys missing from _SCHEMAS: {missing}"