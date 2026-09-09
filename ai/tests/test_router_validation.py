"""Tests for per-module router response schema validation (AUT-141, AUT-1185)."""

import os

os.environ.setdefault("AI_ROUTER_URL", "http://your-9router-instance:port")

import pytest  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

from app.router_client import _cap_payload, _matches_type, _validate_nested, enhance  # noqa: E402


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
    baseline = {"confidence": 0.9, "next_due_date": "2025-06-01", "model": "rule-based-fallback"}
    # Malformed router response: junk fields, wrong-typed fields, valid fields.
    malicious = {
        "model": "General-Use",
        "confidence": "0.999999",        # wrong type — must be dropped, baseline kept
        "interval_km": "five",            # wrong type
        "junk_field": {"x": 1},           # not in whitelist
        "__proto__": {"polluted": True},  # not in whitelist
        "reason": "mileage-based",        # valid
        "next_due_date": "2026-01-01",    # immutable — router must not override baseline
    }
    with patch("app.router_client.route", new=AsyncMock(return_value=malicious)):
        out = await enhance("service-prediction", {}, baseline)
    assert out["confidence"] == 0.9           # baseline preserved
    assert out["reason"] == "mileage-based"   # valid key merged
    assert out["next_due_date"] == "2025-06-01"  # immutable baseline survives
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


def test_cap_payload_truncates_known_field() -> None:
    """AUT-1602: symptoms > 2000 chars must be truncated (per-field cap)."""
    long = "A" * 5000
    out = _cap_payload({"symptoms": long, "make": "Toyota"})
    assert len(out["symptoms"]) == 2000
    assert out["make"] == "Toyota"


def test_cap_payload_truncates_unknown_field_to_default() -> None:
    """Unknown string fields get the 5000-char default cap."""
    out = _cap_payload({"junk": "B" * 8000})
    assert len(out["junk"]) == 5000


def test_cap_payload_enforces_total_budget() -> None:
    """Many mid-size fields trigger total-budget halving pass."""
    big = "X" * 2000
    payload = {f"k{i}": big for i in range(60)}  # ~120k chars raw
    out = _cap_payload(payload)
    import json as _json
    assert len(_json.dumps(out)) <= 100_000
    for v in out.values():
        assert isinstance(v, str)
        assert len(v) <= 2000  # symptom cap was applied first
        assert len(v) <= 1000  # halved at most once


def test_cap_payload_passes_through_short_input() -> None:
    """No truncation when everything is within caps."""
    payload = {"symptoms": "engine misfire", "make": "Toyota"}
    assert _cap_payload(payload) == payload


@pytest.mark.asyncio
async def test_enhance_immutable_diagnostics() -> None:
    """AUT-3150: diagnostics measured fields (severity, cost, items, parts) are immutable."""
    baseline = {
        "severity": "high",
        "estimated_cost": 420.0,
        "cost_range": [300.0, 600.0],
        "items": [{"cause": "coil", "confidence": 0.8, "severity": "high"}],
        "parts_needed": ["NGK BKR6EIX"],
        "model": "rule-based-fallback",
    }
    malicious = {
        "severity": "low",
        "estimated_cost": 1.0,
        "cost_range": [0.0, 0.0],
        "items": [{"cause": "fake", "confidence": 0.1, "severity": "low"}],
        "parts_needed": ["bogus"],
        "recommended_actions": ["do nothing"],
    }
    with patch("app.router_client.route", new=AsyncMock(return_value=malicious)):
        out = await enhance("diagnostics", {}, baseline)
    assert out["severity"] == "high"
    assert out["estimated_cost"] == 420.0
    assert out["cost_range"] == [300.0, 600.0]
    assert out["items"] == baseline["items"]
    assert out["parts_needed"] == ["NGK BKR6EIX"]
    assert out["recommended_actions"] == ["do nothing"]  # valid enrichment merged
    assert out["model"] == "rule-based+ai"


@pytest.mark.asyncio
async def test_enhance_immutable_service_prediction() -> None:
    """AUT-3150: service_prediction measured intervals and due dates are immutable."""
    baseline = {
        "service_type": "major",
        "interval_km": 10000,
        "interval_months": 6,
        "due_in_km": 2000,
        "due_in_days": 90,
        "next_due_km": 12000,
        "next_due_date": "2026-12-01",
        "confidence": 0.9,
        "model": "rule-based-fallback",
    }
    malicious = {
        "service_type": "minor",
        "interval_km": 999,
        "interval_months": 1,
        "due_in_km": 0,
        "due_in_days": 0,
        "next_due_km": 1,
        "next_due_date": "2025-01-01",
        "reason": "router override",
    }
    with patch("app.router_client.route", new=AsyncMock(return_value=malicious)):
        out = await enhance("service-prediction", {}, baseline)
    assert out["service_type"] == "major"
    assert out["interval_km"] == 10000
    assert out["interval_months"] == 6
    assert out["due_in_km"] == 2000
    assert out["due_in_days"] == 90
    assert out["next_due_km"] == 12000
    assert out["next_due_date"] == "2026-12-01"
    assert out["reason"] == "router override"  # valid enrichment merged
    assert out["model"] == "rule-based+ai"
