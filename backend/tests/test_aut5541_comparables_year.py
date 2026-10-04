"""Tests for AUT-5541: valuation comparables must match the
vehicle's model year (a 2009 Toyota Crown was being compared to a
2019 Toyota Crown).

Covers both layers of the fix:
- ``app.services.market_data._same_year`` / ``_build`` — the backend
  no longer aggregates a provider response that ignored the year it
  was sent.
- ``app.services.advisor.value.find_comparables`` — cached rows are
  filtered by year, but so are the individual listings inside them.
"""

import asyncio  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
from types import SimpleNamespace  # noqa: E402

os.environ["DATABASE_URL"] = "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["MARKET_DATA_URL"] = ""
os.environ["MARKET_DATA_API_KEY"] = ""

from app.services.market_data import _build, _same_year  # noqa: E402
from app.services.advisor.value import find_comparables  # noqa: E402


def _crown_listings() -> list[dict]:
    return [
        {"title": "2009 Crown a", "price": 12000.0, "year": 2009},
        {"title": "2009 Crown b", "price": 13000.0, "year": 2009},
        {"title": "2019 Crown a", "price": 45000.0, "year": 2019},
        {"title": "2019 Crown b", "price": 46000.0, "year": 2019},
        {"title": "2021 Crown", "price": 52000.0, "year": 2021},
    ]


# --- market_data: the provider is not trusted to filter years ------

def test_build_ignores_listings_from_another_decade() -> None:
    out = _build({"source": "carsguide", "listings": _crown_listings()}, 2009)
    assert {l["year"] for l in out["listings"]} == {2009}
    assert out["median_price"] == 12500.0
    assert out["sample_size"] == 2


def test_build_no_listings_in_window_is_no_data_not_wrong_median() -> None:
    provider = {"source": "carsguide", "listings": [
        {"title": "2019 Crown a", "price": 45000.0, "year": 2019},
        {"title": "2021 Crown", "price": 52000.0, "year": 2021},
    ]}
    out = _build(provider, 2009)
    assert out["source"] == "fallback"
    assert out["median_price"] is None
    assert out["sample_size"] == 0


def test_build_without_year_keeps_every_listing() -> None:
    """search_market passes no vehicle year — free-text search must
    not start dropping results."""
    provider = {"source": "carsguide", "listings": [
        {"title": "A", "price": 10000.0, "year": 2009},
        {"title": "B", "price": 12000.0, "year": 2019},
    ]}
    out = _build(provider)
    assert out["sample_size"] == 2


def test_same_year_tiers() -> None:
    listings = [{"year": y} for y in (2008, 2009, 2009, 2009, 2010, 2012, 2012, 2012)]
    assert {l["year"] for l in _same_year(listings, 2009)} == {2009}          # exact tier
    assert {l["year"] for l in _same_year(listings, 2006)} == {2008, 2009}     # ±3 tier
    assert {l["year"] for l in _same_year(listings, 1990)} == set()  # past the window
    assert _same_year(listings, None) == listings                              # no year -> no filter


# --- advisor.value: comparables the UI actually renders ------------

class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDb:
    """Minimal stand-in for an AsyncSession: find_comparables only
    needs db.scalars(stmt).all()."""

    def __init__(self, rows):
        self._rows = rows

    async def scalars(self, stmt):
        return _FakeScalars(self._rows)


def _vehicle(**overrides) -> SimpleNamespace:
    base = {
        "id": "v1", "make": "Toyota", "model": "Crown", "year": 2009,
        "condition": "good", "odometer_km": 80_000, "vehicle_type": "car",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _row(year: int, listings: list[dict], source: str = "carsguide") -> SimpleNamespace:
    return SimpleNamespace(year=year, source=source, listings=json.dumps(listings))


def _listing(title: str, price: float, year: int, url: str = "") -> dict:
    return {"title": title, "price": price, "year": year,
            "odometer_km": None, "source": "carsguide", "url": url}


def test_find_comparables_excludes_other_model_years() -> None:
    rows = [
        _row(2009, [
            _listing("2009 Crown a", 12000.0, 2009, "u1"),
            _listing("2009 Crown b", 13000.0, 2009, "u2"),
        ]),
        # The 2012 cache row legitimately holds a 2019 listing —
        # a provider that ignored the year we sent it. It must not
        # be offered as a comparable for a 2009 Crown.
        _row(2012, [
            _listing("2019 Crown", 45000.0, 2019, "u3"),
            _listing("2011 Crown", 15000.0, 2011, "u4"),
        ]),
    ]
    out = asyncio.run(find_comparables(_FakeDb(rows), _vehicle()))
    assert {c["year"] for c in out} == {2009, 2011}
    # Nearest model year first, so the same-year comps lead the set.
    assert [c["year"] for c in out][:2] == [2009, 2009]


def test_find_comparables_empty_when_no_listing_in_window() -> None:
    rows = [_row(2009, [_listing("2019 Crown", 45000.0, 2019, "u")])]
    out = asyncio.run(find_comparables(_FakeDb(rows), _vehicle()))
    assert out == []


def test_find_comparables_uses_row_year_when_listing_year_missing() -> None:
    rows = [_row(2009, [
        {"title": "no-year Crown", "price": 11000.0, "source": "carsguide", "url": "u"},
    ])]
    out = asyncio.run(find_comparables(_FakeDb(rows), _vehicle()))
    assert [c["year"] for c in out] == [2009]
