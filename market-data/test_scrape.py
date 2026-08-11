"""Runnable self-check (no test framework): `python3 test_scrape.py`.

1. Unit: _map_listing + _filter_year on synthetic payloads.
2. Unit: bikesguide gate/parked detection + deterministic empty fallback.
3. Unit: carsguide marketplace-as-list (bike query) never crashes.
4. Live smoke: search_carsguide("toyota camry") must return >=3 priced listings.
5. Live smoke: search_bikesguide("yamaha mt07") must return a deterministic
   empty set + note (domain is parked / FingerprintJS-gated) — never raise.
"""

import asyncio

import bikesguide
import carsguide

_GATED_HTML = """<html><head><title>bikesguide.com.au</title>
<script src="/js/fingerprint/iife.min.js"></script>
<script>var redirect_link='http://www.bikesguide.com.au/search?query=x&tr_uuid=abc';</script>
</head></html>"""

_PARKED_HTML = """<html><head><title>bikesguide.com.au</title>
<script src="https://assets.abovedomains.com/javascript/forsale.min.js"></script>
</head><body><h1>bikesguide.com.au</h1>
<div>This domain may be for sale.</div></body></html>"""


def test_map_and_filter():
    raw = {
        "make": "Toyota", "model": "Crown", "variant": "ROYAL SALOON",
        "manu_year": 1997, "odometer": 67654,
        "price": {"advertised_price": 21990, "driveaway_price": 21990},
        "url": "car/15210772/toyota/crown/sa/melrose-park/limousine",
    }
    l = carsguide._map_listing(raw)
    assert l["title"] == "1997 Toyota Crown ROYAL SALOON", l
    assert l["price"] == 21990.0 and l["year"] == 1997 and l["odometer_km"] == 67654, l
    assert l["source"] == "carsguide" and l["url"].startswith("http"), l

    cars = [
        {"title": "a", "price": 10.0, "year": 2016, "source": "carsguide", "url": "", "odometer_km": 1},
        {"title": "b", "price": 20.0, "year": 2016, "source": "carsguide", "url": "", "odometer_km": 1},
        {"title": "c", "price": 30.0, "year": 2016, "source": "carsguide", "url": "", "odometer_km": 1},
        {"title": "d", "price": 40.0, "year": 1997, "source": "carsguide", "url": "", "odometer_km": 1},
        {"title": "e", "price": 50.0, "year": 1998, "source": "carsguide", "url": "", "odometer_km": 1},
    ]
    assert len(carsguide._filter_year(cars, 2016)) == 3
    assert len(carsguide._filter_year(cars, 1997)) == 5  # <3 exact+near -> keep all
    assert len(carsguide._filter_year(cars, 1990)) == 5  # <3 near -> all
    assert len(carsguide._filter_year(cars, None)) == 5
    print("unit tests OK")


def test_bikesguide_gate():
    assert bikesguide._gated(_GATED_HTML) is True
    assert bikesguide._parked(_GATED_HTML) is False
    assert bikesguide._gated(_PARKED_HTML) is False
    assert bikesguide._parked(_PARKED_HTML) is True
    assert bikesguide._gated('<script id="__NUXT_DATA__">[]</script>') is False
    print("bikesguide gate/parked detection OK")


def test_carsguide_marketplace_list():
    """Bike queries render marketplace as a list (empty) — parser must not crash."""
    import json
    arr = [
        None,
        {"data": [{"siteWideSearch-yamaha-mt07": {"data": {"marketplace": [], "editorial": {}, "showroom": {}}}}]},
    ]
    html = '<script id="__NUXT_DATA__">%s</script>' % json.dumps(arr)
    assert carsguide._parse_nuxt_listings(html) == []
    print("carsguide marketplace-as-list OK")


async def live_smoke():
    result = await carsguide.search_carsguide("toyota camry")
    assert result["source"] == "carsguide", result
    priced = [l for l in result["listings"] if l.get("price")]
    assert len(priced) >= 3, f"expected >=3 priced listings, got {len(priced)}"
    sample = priced[0]
    for key in ("title", "price", "year", "odometer_km", "source", "url"):
        assert key in sample, key
    print(f"live smoke OK: {len(priced)} listings, sample={sample}")
    return result


async def bikesguide_smoke():
    result = await bikesguide.search_bikesguide("yamaha mt07")
    assert result["source"] == "bikesguide", result
    assert isinstance(result["listings"], list), result
    assert "note" in result, result
    print(f"bikesguide smoke OK: {len(result['listings'])} listings, note={result.get('note')}")
    return result


if __name__ == "__main__":
    test_map_and_filter()
    test_bikesguide_gate()
    test_carsguide_marketplace_list()
    asyncio.run(live_smoke())
    asyncio.run(bikesguide_smoke())
    print("ALL OK")
