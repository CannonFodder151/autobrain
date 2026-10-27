"""Tests for market_data_scraper (AUT-5868)."""

import pytest

from app.services.market_data_scraper import (
    _parse_nuxt_listings,
    _map_listing,
    _filter_year,
    _parse_categories,
    _extract_vehicle_from_rego,
    _CATEGORIES_BY_TYPE,
    _SERVICE_GROUPS,
)


def test_parse_nuxt_listings_empty():
    """Empty HTML returns empty list."""
    assert _parse_nuxt_listings("<html></html>") == []


def test_parse_nuxt_listings_no_script():
    """HTML without __NUXT_DATA__ returns empty list."""
    html = '<html><body><div>No script here</div></body></html>'
    assert _parse_nuxt_listings(html) == []


def test_map_listing_basic():
    """Basic listing mapping works."""
    raw = {
        "manu_year": 2020,
        "make": "Toyota",
        "model": "Camry",
        "variant": "Ascent",
        "price": {"advertised_price": 25000},
        "odometer": 50000,
        "url": "/cars/toyota/camry/123",
    }
    listing = _map_listing(raw)
    assert listing is not None
    assert listing["title"] == "2020 Toyota Camry Ascent"
    assert listing["price"] == 25000.0
    assert listing["year"] == 2020
    assert listing["odometer_km"] == 50000
    assert listing["source"] == "carsguide"
    assert listing["url"] == "https://www.carsguide.com.au/cars/toyota/camry/123"


def test_map_listing_price_as_number():
    """Price as plain number works."""
    raw = {
        "manu_year": 2019,
        "make": "Honda",
        "model": "Civic",
        "price": 20000,
    }
    listing = _map_listing(raw)
    assert listing["price"] == 20000.0


def test_map_listing_missing_fields():
    """Missing fields handled gracefully."""
    raw = {}
    listing = _map_listing(raw)
    assert listing is not None
    assert listing["title"] == ""
    assert listing["price"] is None
    assert listing["year"] is None
    assert listing["odometer_km"] is None


def test_filter_year_exact_match():
    """Exact year match returns exact matches when >= 3."""
    listings = [
        {"year": 2020, "price": 1000},
        {"year": 2020, "price": 2000},
        {"year": 2020, "price": 3000},
        {"year": 2019, "price": 4000},
    ]
    filtered = _filter_year(listings, 2020)
    assert len(filtered) == 3
    assert all(l["year"] == 2020 for l in filtered)


def test_filter_year_nearby_fallback():
    """Nearby years used when exact matches < 3."""
    listings = [
        {"year": 2020, "price": 1000},
        {"year": 2021, "price": 2000},
        {"year": 2019, "price": 3000},
        {"year": 2018, "price": 4000},
    ]
    filtered = _filter_year(listings, 2020)
    assert len(filtered) == 3
    assert all(abs(l["year"] - 2020) <= 1 for l in filtered)


def test_filter_year_none():
    """None year returns all listings."""
    listings = [
        {"year": 2020, "price": 1000},
        {"year": 2019, "price": 2000},
    ]
    filtered = _filter_year(listings, None)
    assert len(filtered) == 2


def test_parse_categories_basic():
    """Category parsing extracts slugs correctly."""
    html = '''
    <html>
    <a href="https://www.supercheapauto.com.au/spare-parts/braking">Braking</a>
    <a href="https://www.supercheapauto.com.au/spare-parts/cooling">Cooling</a>
    <a href="https://www.supercheapauto.com.au/spare-parts/engine-parts">Engine Parts</a>
    </html>
    '''
    categories = _parse_categories(html)
    assert len(categories) == 3
    slugs = [c["slug"] for c in categories]
    assert "braking" in slugs
    assert "cooling" in slugs
    assert "engine-parts" in slugs
    for c in categories:
        assert "name" in c
        assert "service_group" in c
        assert "part_category" in c
        assert "url" in c


def test_parse_categories_dedup():
    """Duplicate slugs are deduplicated."""
    html = '''
    <html>
    <a href="https://www.supercheapauto.com.au/spare-parts/braking">Braking 1</a>
    <a href="https://www.supercheapauto.com.au/spare-parts/braking">Braking 2</a>
    <a href="https://www.supercheapauto.com.au/spare-parts/cooling">Cooling</a>
    </html>
    '''
    categories = _parse_categories(html)
    assert len(categories) == 2


def test_parse_categories_excludes_known():
    """Known non-category slugs are excluded."""
    html = '''
    <html>
    <a href="https://www.supercheapauto.com.au/spare-parts/spare-parts">Spare Parts</a>
    <a href="https://www.supercheapauto.com.au/spare-parts/vehicle">Vehicle</a>
    <a href="https://www.supercheapauto.com.au/spare-parts/parts-guide">Parts Guide</a>
    <a href="https://www.supercheapauto.com.au/spare-parts/braking">Braking</a>
    </html>
    '''
    categories = _parse_categories(html)
    assert len(categories) == 1
    assert categories[0]["slug"] == "braking"


def test_extract_vehicle_from_rego_valid():
    """Valid JSON with vehicle data returns parsed dict."""
    html = '{"vehicle": {"make": "Toyota", "model": "Camry", "year": 2020, "colour": "White"}}'
    vehicle = _extract_vehicle_from_rego(html)
    assert vehicle is not None
    assert vehicle["make"] == "Toyota"
    assert vehicle["model"] == "Camry"
    assert vehicle["year"] == 2020
    assert vehicle["colour"] == "White"


def test_extract_vehicle_from_rego_invalid_json():
    """Invalid JSON returns None."""
    assert _extract_vehicle_from_rego("not json") is None


def test_extract_vehicle_from_rego_no_vehicle():
    """JSON without vehicle key returns None."""
    assert _extract_vehicle_from_rego('{"other": "data"}') is None


def test_categories_by_type_mapping():
    """Category mappings are correct."""
    assert _CATEGORIES_BY_TYPE["braking"] == "brakes"
    assert _CATEGORIES_BY_TYPE["engine-parts"] == "engine"
    assert _CATEGORIES_BY_TYPE["motorcycle-parts"] == "motorcycle"
    # Unknown slugs default to "other" via .get() in parse_categories
    assert _CATEGORIES_BY_TYPE.get("unknown", "other") == "other"


def test_service_groups_mapping():
    """Service group mappings are correct."""
    assert _SERVICE_GROUPS["brakes"] == "Brakes"
    assert _SERVICE_GROUPS["engine"] == "Engine"
    # Unknown categories default to "Other" via .get() in parse_categories
    assert _SERVICE_GROUPS.get("unknown", "Other") == "Other"