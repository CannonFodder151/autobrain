"""Tests for the Supercheap Auto parts-guide scraper (AUT-1792).

Run standalone: python3 test_supercheap.py
Also runs under pytest: pytest test_supercheap.py -v
"""

import asyncio

from supercheap import (
    build_catalogue,
    search_supercheap,
    SERVICE_GROUPS,
)


def test_build_catalogue_structure():
    cat = build_catalogue("ABC123", "VIC", "Toyota", "HiLux", 2021, "2.8L Turbo Diesel")
    assert cat["source"] == "supercheap"
    assert cat["vehicle"]["rego"] == "ABC123"
    assert cat["vehicle"]["make"] == "Toyota"
    assert len(cat["parts"]) >= 10, f"expected >=10 parts, got {len(cat['parts'])}"
    assert len(cat["categories"]) >= 4
    part_keys = {"name", "sku", "category", "service_group", "service_group_key", "brand",
                 "supplier", "unit_cost", "quantity", "notes"}
    for p in cat["parts"]:
        assert part_keys.issubset(p.keys()), f"missing keys in {p.keys()}"
        assert p["supplier"] == "Supercheap Auto"
        assert p["brand"], f"missing brand in {p['name']}"
        assert p["service_group"] in SERVICE_GROUPS.values(), f"bad group: {p['service_group']}"
    print(f"structure OK: {len(cat['parts'])} parts, {len(cat['categories'])} groups")


def test_diesel_has_glow_plugs():
    cat = build_catalogue("DEF456", "QLD", "Ford", "Ranger", 2022, "2.0L Bi-Turbo Diesel")
    names = [p["name"] for p in cat["parts"]]
    assert "Glow Plugs" in names, f"diesel must have glow plugs, got: {names}"
    assert "Spark Plugs" not in names, f"no spark plugs for diesel, got: {names}"
    print("diesel OK: glow plugs present, spark plugs absent")


def test_petrol_spark_plugs():
    cat = build_catalogue("GHI789", "NSW", "Toyota", "Camry", 2021, "2.5L 4-cyl")
    names = [p["name"] for p in cat["parts"]]
    assert "Spark Plugs" in names, f"petrol should have spark plugs, got: {names}"
    plugs = [p for p in cat["parts"] if p["category"] == "spark_plugs"]
    assert plugs[0]["quantity"] == 4, f"4-cyl should have 4 plugs, got {plugs[0]['quantity']}"
    print("petrol spark plugs OK")


def test_v6_spark_plugs():
    cat = build_catalogue("V6A", "VIC", "BMW", "3 Series", 2020, "Inline-6")
    plugs = [p for p in cat["parts"] if p["category"] == "spark_plugs"]
    assert plugs[0]["quantity"] == 6, f"inline-6 should have 6 plugs, got {plugs[0]['quantity']}"
    print("v6 spark plugs OK")


def test_coil_on_plug_ignition_leads_absent():
    cat = build_catalogue("COP", "WA", "Mazda", "CX-5", 2023, "2.5L 4-cyl coil-on-plug")
    names = [p["name"] for p in cat["parts"]]
    assert "Ignition Lead Set" not in names, f"coil-on-plug should have no leads, got: {names}"
    print("coil-on-plug OK: no leads")


def test_search_deterministic_mode():
    result = asyncio.run(search_supercheap("VICTCR", "VIC", "Toyota", "Crown", 1997, "2.5L Twin-Turbo"))
    assert result["source"] == "supercheap", result
    assert result["mode"] == "deterministic", result
    assert len(result["parts"]) >= 10
    assert isinstance(result["categories"], list)
    print(f"deterministic search OK: {len(result['parts'])} parts")


if __name__ == "__main__":
    test_build_catalogue_structure()
    test_diesel_has_glow_plugs()
    test_petrol_spark_plugs()
    test_v6_spark_plugs()
    test_coil_on_plug_ignition_leads_absent()
    test_search_deterministic_mode()
    print("ALL OK")
