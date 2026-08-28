"""Tests for the SCA parts-guide deterministic fallback engine."""

import os

os.environ.setdefault("AI_ROUTER_URL", "http://your-9router-instance:port")

from app.fallbacks.parts_guide import (
    build_inventory_from_categories,
    format_vehicle_str,
    suggest_parts_for_service,
)


def test_format_vehicle_str():
    assert format_vehicle_str({"make": "Toyota", "model": "Corolla", "year": 2020}) == "2020 Toyota Corolla"
    assert format_vehicle_str({"make": "BMW", "model": None, "year": None}) == "BMW"
    assert format_vehicle_str(None) == "the vehicle"


def test_build_inventory_from_categories_shape():
    cats = [
        {"slug": "braking", "name": "Braking", "service_group": "Brakes",
         "part_category": "brakes", "url": "https://www.supercheapauto.com.au/spare-parts/braking"},
        {"slug": "cooling", "name": "Cooling", "service_group": "Cooling",
         "part_category": "cooling", "url": "https://www.supercheapauto.com.au/spare-parts/cooling"},
    ]
    inv = build_inventory_from_categories(cats, {"make": "Toyota", "model": "Corolla", "year": 2020})
    assert len(inv) == 2
    for p in inv:
        assert p["supplier"] == "Supercheap Auto"
        assert p["source"] == "supercheap"
        assert p["category"] and p["name"] and p["sku"]
        assert isinstance(p["min_quantity"], int) and isinstance(p["unit_cost"], float)


def test_build_inventory_unknown_category_falls_back():
    inv = build_inventory_from_categories(
        [{"slug": "novelty", "name": "Novelty", "service_group": "Other",
          "part_category": "other", "url": "x"}],
        {"make": "Toyota", "model": "Corolla", "year": 2020},
    )
    assert inv[0]["name"] == "Novelty"
    assert inv[0]["category"] == "other"


def test_suggest_prefers_inventory_first():
    inventory = [{
        "name": "Brake Pads", "category": "brake_pads", "quantity": 2,
        "service_group": "Brakes", "source": "inventory", "unit_cost": 49.0,
    }]
    sca = [{
        "name": "Brake Pads", "category": "brake_pads", "service_group": "Brakes",
        "source": "supercheap", "unit_cost": 55.0,
    }]
    suggested = suggest_parts_for_service("brake_pads", inventory, sca)
    assert len(suggested) >= 1
    # Inventory part must appear and be labelled as inventory source.
    inv_first = [p for p in suggested if p.get("source") == "inventory"]
    assert inv_first, "inventory parts must be preferred over SCA suggestions"
    assert all(p["source"] != "supercheap" for p in inv_first)


def test_suggest_falls_back_to_sca_when_inventory_empty():
    inventory: list[dict] = []
    sca = [{
        "name": "Spark Plugs", "category": "spark_plugs", "service_group": "Ignition",
        "source": "supercheap", "unit_cost": 12.0,
    }]
    suggested = suggest_parts_for_service("spark_plugs", inventory, sca)
    assert any(p.get("source") == "supercheap" for p in suggested)
