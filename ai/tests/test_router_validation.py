"""Tests for per-module router response schema validation (AUT-141, AUT-1185)."""

import os

os.environ.setdefault("AI_ROUTER_URL", "http://your-9router-instance:port")

import pytest  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

from app.router_client import _matches_type, _validate_nested, enhance  # noqa: E402


def test_matches_type() -> None:
    assert _matches_type("low", (str,))
    assert _matches_type(3, (int, float))
    assert _matches_type(3.5, (int, float))
    assert _matches_type(None, (str, type(None)))
    assert not _matches_type(3, (str,))
    assert not _matches_type("3", (int, float))
    assert not _matches_type(None, (str,))
    assert not _matches_type(True, (int, float))  # bool is not a number


def test_validate_nested_depth_and_length() -> None:
    """AUT-1185 FINDING-02: nested structure must be depth/length capped."""
    assert _validate_nested({"a": [1, 2, {"b": "c"}]})
    deep = current = {}
    for _ in range(20):
        current["child"] = {}
        current = current["child"]
    assert not _validate_nested(deep)                       # too deep
    assert not _validate_nested([1] * 101)                  # array too long
    assert _validate_nested([1] * 100)                      # exactly at cap
    assert not _validate_nested({"a": [[[[[object()]]]]]})  # non-primitive leaf


@pytest.mark.asyncio
async def test_enhance_drops_nested_too_deep(monkeypatch) -> None:
    """Router response with over-deep nested dict must be dropped."""
    baseline = {"confidence": 0.9, "model": "rule-based-fallback"}
    malicious = {
        "reason": {"a": {"b": {"c": {"d": {"e": "too deep"}}}}},
    }
    with patch("app.router_client.route", new=AsyncMock(return_value=malicious)):
        out = await enhance("service-prediction", {}, baseline)
    assert "reason" not in out  # dropped due to depth
    assert out == baseline


@pytest.mark.asyncio
async def test_enhance_drops_nested_array_too_long(monkeypatch) -> None:
    """Router response with over-long array must be dropped."""
    baseline = {"confidence": 0.9, "model": "rule-based-fallback"}
    malicious = {
        "items": [1] * 101,
    }
    with patch("app.router_client.route", new=AsyncMock(return_value=malicious)):
        out = await enhance("diagnostics", {}, baseline)
    assert "items" not in out
    assert out == baseline


@pytest.mark.asyncio
async def test_enhance_drops_junk_and_typed_keys() -> None:
    baseline = {"confidence": 0.9, "model": "rule-based-fallback"}
    # Malformed router response: junk fields, wrong-typed fields, valid fields.
    malicious = {
        "model": "General-Use",
        "confidence": "0.999999",        # wrong type — must be dropped, baseline kept
        "interval_km": "five",            # wrong type
        "junk_field": {"x": 1},           # not in whitelist
        "__proto__": {"polluted": True},  # not in whitelist
        "reason": "mileage-based",        # valid
        "next_due_date": "2026-01-01",    # valid
    }
    with patch("app.router_client.route", new=AsyncMock(return_value=malicious)):
        out = await enhance("service-prediction", {}, baseline)
    assert out["confidence"] == 0.9           # baseline preserved
    assert out["reason"] == "mileage-based"   # valid key merged
    assert out["next_due_date"] == "2026-01-01"
    assert "interval_km" not in out
    assert "junk_field" not in out
    assert "__proto__" not in out
    assert out["model"] == "rule-based+ai"


@pytest.mark.asyncio
async def test_enhance_no_schema_module_gets_no_enrichment() -> None:
    baseline = {"model": "rule-based-fallback"}
    with patch("app.router_client.route", new=AsyncMock(return_value={"anything": 1})):
        out = await enhance("unknown-module", {}, baseline)
    assert out == baseline  # untouched: no schema, nothing merges


@pytest.mark.asyncio
async def test_enhance_immutable_never_overridden() -> None:
    baseline = {"estimated_value": 30000.0, "model": "rule-based-fallback"}
    malicious = {"estimated_value": 1.0, "rrp": 60000.0}
    with patch("app.router_client.route", new=AsyncMock(return_value=malicious)):
        out = await enhance("resale", {}, baseline)
    assert out["estimated_value"] == 30000.0  # immutable survives
    assert out["rrp"] == 60000.0              # valid enrichment merged
