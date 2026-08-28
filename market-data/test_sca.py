"""Runnable self-check (no test framework): `python3 test_sca.py`.

1. Unit: _parse_categories extracts the SCA parts-guide taxonomy and maps each
   slug to a normalised category + service group.
2. Unit: _extract_vehicle_from_rego parses a FindRegoVehicle JSON payload.
3. Unit: _empty produces a deterministic, never-erroring fallback envelope.
4. Live smoke: search_sca on a bare vehicle (no rego) returns categories from
   the live SCA parts-guide page (or a clean empty + note if geo-blocked).
"""

import asyncio

import sca

_SAMPLE_HTML = """
<html><body>
<a href="https://www.supercheapauto.com.au/spare-parts/braking">Brakes</a>
<a href="https://www.supercheapauto.com.au/spare-parts/cooling">Cooling</a>
<a href="https://www.supercheapauto.com.au/spare-parts/engine-parts">Engine</a>
<a href="https://www.supercheapauto.com.au/spare-parts/manuals">Manuals</a>
<a href="https://www.supercheapauto.com.au/spare-parts/spare-parts">root</a>
</body></html>
"""


def test_parse_categories_mapping():
    cats = sca._parse_categories(_SAMPLE_HTML)
    slugs = [c["slug"] for c in cats]
    assert slugs == ["braking", "cooling", "engine-parts", "manuals"], slugs
    braking = cats[0]
    assert braking["part_category"] == "brakes"
    assert braking["service_group"] == "Brakes"
    assert braking["url"].endswith("/braking")
    print("parse_categories mapping OK")


def test_parse_categories_dedup():
    html = """
    <a href="https://www.supercheapauto.com.au/spare-parts/braking">Brakes</a>
    <a href="https://www.supercheapauto.com.au/spare-parts/braking">Again</a>
    <a href="https://www.supercheapauto.com.au/spare-parts/spare-parts">root</a>
    """
    cats = sca._parse_categories(html)
    assert len(cats) == 1, cats


def test_extract_vehicle_from_rego():
    payload = '{"vehicle": {"make": "Toyota", "model": "Corolla", "year": 2020}}'
    vehicle = sca._extract_vehicle_from_rego(payload)
    assert vehicle is not None
    assert vehicle["make"] == "Toyota" and vehicle["model"] == "Corolla"
    assert vehicle["year"] == 2020
    assert sca._extract_vehicle_from_rego("not json") is None


def test_empty_envelope_is_safe():
    env = sca._empty("gated: nope")
    assert env["source"] == "supercheap"
    assert env["categories"] == []
    assert env["note"] == "gated: nope"


async def live_smoke():
    result = await sca.search_sca(make="Toyota", model="Camry", year=2020)
    assert result["source"] == "supercheap"
    assert isinstance(result["categories"], list)
    print(f"live smoke OK: {len(result['categories'])} categories, "
          f"vehicle={result['vehicle'] is not None}")


if __name__ == "__main__":
    test_parse_categories_mapping()
    test_parse_categories_dedup()
    test_extract_vehicle_from_rego()
    test_empty_envelope_is_safe()
    asyncio.run(live_smoke())
    print("ALL OK")
