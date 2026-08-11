"""Runnable self-check (no test framework): `python3 test_scrape.py`.

1. Unit: _map_listing + _filter_year on synthetic payloads.
2. Unit: bikesguide gate detection + empty deterministic fallback.
3. Live smoke: search_carsguide("toyota camry") must return >=3 priced listings.
"""

import asyncio

import bikesguide
import carsguide

_GATED_HTML = """<html><head><title>bikesguide.com.au</title>
<script src="/js/fingerprint/iife.min.js"></script>
<script>var redirect_link='http://www.bikesguide.com.au/search?query=x&tr_uuid=abc';</script>
</head></html>"""


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
    assert bikesguide._gated('<script id="__NUXT_DATA__">[]</script>') is False
    print("bikesguide gate detection OK")


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
    assert "listings" in result, result
    print(f"bikesguide smoke OK: {len(result['listings'])} listings, note={result.get('note')}")
    return result


if __name__ == "__main__":
    test_map_and_filter()
    test_bikesguide_gate()
    asyncio.run(live_smoke())
    asyncio.run(bikesguide_smoke())
    print("ALL OK")
