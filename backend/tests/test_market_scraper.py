"""Tests for the local market-data scraper package (AUT-4113).

Covers:
- Pure parsing functions (CarsGuide Nuxt data, BikesGuide, SCA categories)
- Import robustness in both module and direct-script invocation modes
"""

import json
import os
import sys

# Test pure parsing (no network, no browser)
from app.services.market_scraper.carsguide import _map_listing
from app.services.market_scraper.sca import _parse_categories, _extract_vehicle_from_rego


def test_carsguide_map_listing() -> None:
    raw = {
        "price": {"advertised_price": "120,000"},
        "manu_year": 1997,
        "make": "Toyota",
        "model": "Supra",
        "variant": "RZ",
        "odometer": "85000",
        "url_cg": "/cars/toyota/supra/123",
    }
    mapped = _map_listing(raw)
    assert mapped["price"] == 120000.0
    assert mapped["year"] == 1997
    assert mapped["title"] == "1997 Toyota Supra RZ"
    assert mapped["odometer_km"] == 85000
    assert mapped["source"] == "carsguide"
    assert mapped["url"] == "https://www.carsguide.com.au/cars/toyota/supra/123"


def test_sca_parse_categories() -> None:
    """SCA parts-guide menu extraction from HTML."""
    html = """
    <a href="https://www.supercheapauto.com.au/spare-parts/braking">Braking</a>
    <a href="https://www.supercheapauto.com.au/spare-parts/cooling">Cooling</a>
    <a href="https://www.supercheapauto.com.au/spare-parts/engine-parts">Engine Parts</a>
    """
    cats = _parse_categories(html)
    assert len(cats) == 3
    assert cats[0]["slug"] == "braking"
    assert cats[0]["part_category"] == "brakes"
    assert cats[0]["service_group"] == "Brakes"
    assert cats[1]["slug"] == "cooling"
    assert cats[2]["slug"] == "engine-parts"


def test_sca_vehicle_extraction() -> None:
    payload = {
        "vehicle": {"make": "Mazda", "model": "MX-5", "year": 2020, "colour": "Red"}
    }
    vehicle = _extract_vehicle_from_rego(json.dumps(payload))
    assert vehicle["make"] == "Mazda"
    assert vehicle["model"] == "MX-5"
    assert vehicle["year"] == 2020

    # Malformed/non-vehicle JSON returns None
    assert _extract_vehicle_from_rego("not json") is None
    assert _extract_vehicle_from_rego("{}") is None


def test_browser_script_import_resolution() -> None:
    """Verify browser.py's direct-script import block resolves without ImportError.

    The scraper runs as a subprocess (`python browser.py ...`) from the
    market_scraper package dir, so its `else:` branch (sys.path.insert + bare
    `import carsguide` / `import sca`) must succeed. We exec the module source
    with `__name__ != "__main__"` so the script's network entrypoint is skipped,
    then assert the hoisted names exist.
    """
    import importlib.util

    script = "/home/node/autobrain/backend/app/services/market_scraper/browser.py"
    with open(script) as f:
        source = f.read()

    # Strip the `if __name__ == "__main__":` tail so we only exec imports + defs.
    marker = 'if __name__ == "__main__":'
    assert marker in source
    source = source.split(marker, 1)[0]

    spec = importlib.util.spec_from_file_location("browser_script", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert hasattr(module, "scrape_sca")
    assert hasattr(module, "scrape_bikesguide")
    assert hasattr(module, "sca")  # hoisted, not a lazy `from sca import`
    assert hasattr(module, "carsguide")
    assert hasattr(module, "_NUXT_SCRIPT")