"""Tests for the SCA parts-guide service + suggested-service parts prefill (AUT-1792)."""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["MARKET_DATA_URL"] = ""
os.environ["MARKET_DATA_API_KEY"] = ""
os.environ["AI_ROUTER_URL"] = "http://your-9router-instance:port"

from unittest.mock import AsyncMock, patch  # noqa: E402

import pytest  # noqa: E402

from app.services.sca_parts import get_sca_parts_guide, suggest_service_parts  # noqa: E402
from app.models.part import Part  # noqa: E402


def _sample_catalogue():
    return {
        "source": "supercheap",
        "mode": "deterministic",
        "vehicle": {"rego": "VICTCR", "state": "VIC", "make": "Toyota", "model": "Crown", "year": 1997},
        "categories": [{"service_group_key": "oils_fluids", "service_group": "Engine Oils & Fluids", "count": 2}],
        "parts": [
            {"name": "engine oil", "sku": None, "category": "engine_oil",
             "service_group": "Engine Oils & Fluids", "service_group_key": "oils_fluids",
             "brand": "castrol", "supplier": "Supercheap Auto", "unit_cost": 54.99,
             "quantity": 5, "notes": "5L"},
            {"name": "engine oil filter", "category": "oil_filter",
             "service_group": "Filters", "service_group_key": "filters", "brand": "ryco",
             "supplier": "Supercheap Auto", "unit_cost": 12.95, "quantity": 1},
        ],
        "note": "canonical",
    }


@pytest.mark.asyncio
async def test_get_sca_parts_guide_maps_provider_and_formats():
    db = AsyncMock()
    with patch("app.services.sca_parts._fetch_provider", AsyncMock(return_value=_sample_catalogue())), \
         patch("app.services.ai_client.format_parts", AsyncMock(return_value=None)):
        out = await get_sca_parts_guide(db, "vid", make="Toyota", model="Crown", year=1997)
    assert out["source"] == "supercheap"
    assert out["formatted_with"] == "rule-based"  # router down -> deterministic baseline
    assert len(out["parts"]) == 2
    assert out["parts"][0]["name"] == "engine oil"
    assert out["categories"][0]["service_group"] == "Engine Oils & Fluids"


@pytest.mark.asyncio
async def test_get_sca_parts_guide_fallback_on_unavailable():
    db = AsyncMock()
    with patch("app.services.sca_parts._fetch_provider", AsyncMock(return_value=None)), \
         patch("app.services.ai_client.format_parts", AsyncMock(return_value=None)):
        out = await get_sca_parts_guide(db, "vid", make="Toyota", model="Crown", year=1997)
    assert out["source"] == "fallback"
    assert out["mode"] == "unavailable"
    assert out["parts"] == []


class _FakeVehicle:
    def __init__(self):
        self.id = "vid"
        self.make = "Toyota"
        self.model = "Crown"
        self.year = 1997
        self.engine = ""
        self.rego = "VICTCR"
        self.state = "VIC"


class _FakeDb:
    def __init__(self, inventory):
        self._inventory = inventory

    async def get(self, model, pk):
        return _FakeVehicle()

    async def scalars(self, stmt):
        class _R:
            def __init__(self, rows):
                self._rows = rows
            def __await__(self):
                async def _a():
                    return self
                return _a().__await__()
            def __iter__(self):
                return iter(self._rows)
        return _R(self._inventory)


@pytest.mark.asyncio
async def test_suggest_service_parts_prefers_inventory_then_sca():
    # One inventory part for 'oil_filter' already stocked; SCA fills the rest.
    inv = Part(vehicle_id="vid", name="Ryco Oil Filter", category="oil_filter",
               supplier="Repco", unit_cost=11.5, min_quantity=2)
    db = _FakeDb([inv])
    with patch("app.services.sca_parts.get_sca_parts_guide",
               AsyncMock(return_value=_sample_catalogue())):
        suggested = await suggest_service_parts(db, _FakeVehicle(), "scheduled")
    sources = [s["source"] for s in suggested]
    # oil_filter comes from inventory, engine_oil from sca
    assert "inventory" in sources and "sca" in sources
    inv_part = [s for s in suggested if s["source"] == "inventory"][0]
    assert inv_part["name"] == "Ryco Oil Filter"
    assert inv_part["supplier"] == "Repco"
