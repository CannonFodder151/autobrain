"""AUT-2616: rego-lookup-api only scrapes vin/make/model/year/colour/body_type
from state sites, so the provider path returned empty `engine`/`transmission`
and the vehicle-screen table showed blank Engine/Transmission rows.

Fix: backfill engine/transmission from the local spec table by (make, model)
after provider success. When the provider returns nothing, the table now
answers; the same path also works after a partial scrape.
"""

import pytest

from app.services.rego import (
    _backfill_spec,
    _backfill_spec_from_vin,
    _backfill_year_from_vin,
    _map_provider,
)


def _provider_payload(make: str, model: str, year: int = 2020, vin: str | None = None) -> dict:
    """Shape returned by rego-lookup-api (no engine/transmission)."""
    v: dict = {
        "registration_number": "TCRWN",
        "make": make,
        "model": model,
        "year": year,
        "colour": "BLACK",
        "body_type": "SEDAN",
    }
    if vin:
        v["vin"] = vin
    return {"vehicle": v}


def test_backfill_spec_exact_match():
    engine, transmission = _backfill_spec("Toyota", "Camry")
    assert engine == "2.5L 4-cyl"
    assert transmission == "Automatic"


def test_backfill_spec_case_insensitive():
    engine, transmission = _backfill_spec("toyota", "camry")
    assert engine == "2.5L 4-cyl"
    assert transmission == "Automatic"


def test_backfill_spec_make_only_fallback():
    """Different model under same make falls back to the first match."""
    engine, transmission = _backfill_spec("Toyota", "Unknown Model")
    assert engine  # any Toyota row
    assert transmission


def test_backfill_spec_unknown_make():
    engine, transmission = _backfill_spec("Unobtainium", "Vapor")
    assert engine == ""
    assert transmission == ""


def test_backfill_spec_empty_make():
    engine, transmission = _backfill_spec("", "")
    assert engine == ""
    assert transmission == ""


def test_backfill_vin_wmi_known():
    engine, transmission = _backfill_spec_from_vin("JTDBR32E8300ABCDE")
    # JTD -> Toyota Camry
    assert engine == "2.5L 4-cyl"
    assert transmission == "Automatic"


def test_backfill_vin_wmi_unknown():
    engine, transmission = _backfill_spec_from_vin("ZZZZZZZZZZZZZZZZZ")
    assert engine == ""
    assert transmission == ""


def test_backfill_vin_too_short():
    engine, transmission = _backfill_spec_from_vin("JN")
    assert engine == ""
    assert transmission == ""


def test_backfill_vin_none():
    engine, transmission = _backfill_spec_from_vin(None)
    assert engine == ""
    assert transmission == ""


def test_backfill_year_from_vin_known():
    # Year code is VIN position 10 (0-indexed 9), ISO 3779.
    assert _backfill_year_from_vin("JTDBR32E810012345") == 2031  # pos9='1'
    assert _backfill_year_from_vin("1HGB02E35D9123456") == 2013  # pos9='D'
    assert _backfill_year_from_vin("WVWZZZ1JZYW000001") == 2030  # pos9='Y'


def test_backfill_year_from_vin_none():
    assert _backfill_year_from_vin(None) is None


def test_backfill_year_from_vin_too_short():
    assert _backfill_year_from_vin("JT") is None


def test_backfill_year_from_vin_unknown_code():
    # 'I', 'O', 'Q', 'Z' are not valid VIN year codes — returns None.
    # Put the unknown code in position 10 (0-indexed 9).
    assert _backfill_year_from_vin("JTDBR32E8I00ABCDE") is None  # 'I'
    assert _backfill_year_from_vin("JTDBR32E8O00ABCDE") is None  # 'O'
    assert _backfill_year_from_vin("JTDBR32E8Q00ABCDE") is None  # 'Q'
    assert _backfill_year_from_vin("JTDBR32E8Z00ABCDE") is None  # 'Z'
    """The rego-lookup-api shape has no engine/transmission — backfill from
    the local spec table instead of returning blanks."""
    result = _map_provider(_provider_payload("Toyota", "Camry"), "TCRWN", "VIC")
    assert result is not None
    assert result["make"] == "Toyota"
    assert result["model"] == "Camry"
    assert result["engine"] == "2.5L 4-cyl"
    assert result["transmission"] == "Automatic"
    assert result["source"] == "provider"


def test_map_provider_backfills_from_vin_when_make_unknown():
    result = _map_provider(
        _provider_payload("UnknownMake", "Mystery", vin="JTDBR32E830012345"),
        "TCRWN", "VIC",
    )
    assert result is not None
    # VIN decodes to Toyota Camry; that entry should backfill the spec
    assert result["engine"] == "2.5L 4-cyl"
    assert result["transmission"] == "Automatic"


def test_map_provider_keeps_provider_engine_when_present():
    payload = _provider_payload("Toyota", "Camry")
    payload["vehicle"]["engine"] = "3.5L V6 Hybrid"
    payload["vehicle"]["transmission"] = "CVT (e-CVT)"
    result = _map_provider(payload, "TCRWN", "VIC")
    assert result is not None
    # Provider value wins over the spec table
    assert result["engine"] == "3.5L V6 Hybrid"
    assert result["transmission"] == "CVT (e-CVT)"


def test_map_provider_blank_when_no_match():
    """Unknown make+model+VIN stays blank — we never guess specs for the UI."""
    result = _map_provider(
        _provider_payload("Unobtainium", "Vapor"), "TCRWN", "VIC",
    )
    assert result is not None
    assert result["engine"] == ""
    assert result["transmission"] == ""


def test_map_provider_explicit_failure_returns_none():
    result = _map_provider(
        {"success": False, "message": "plate not found"},
        "TCRWN", "VIC",
    )
    assert result is None


def test_map_provider_year_range_fallback():
    """Free-tier plateapi returns a year range — pick the lowest year."""
    result = _map_provider(
        {"vehicle": {"make": "Toyota", "model": "Camry", "lowest_year": 2018, "highest_year": 2021}},
        "TCRWN", "VIC",
    )
    assert result is not None
    assert result["year"] == 2018


def test_map_provider_year_uses_year_field_first():
    result = _map_provider(
        {"vehicle": {"make": "Toyota", "model": "Camry", "year": 2019}},
        "TCRWN", "VIC",
    )
    assert result is not None
    assert result["year"] == 2019


def test_map_provider_backfills_year_from_vin():
    """When provider has no year field, decode it from VIN position 10."""
    result = _map_provider(
        {"vehicle": {"make": "Toyota", "model": "Camry", "vin": "JTDBR32E810012345"}},
        "TCRWN", "VIC",
    )
    assert result is not None
    assert result["year"] == 2031


def test_map_provider_year_none_stays_none():
    """VIN without valid year code leaves year as None."""
    result = _map_provider(
        {"vehicle": {"make": "Toyota", "model": "Camry", "vin": "JT"}},
        "TCRWN", "VIC",
    )
    assert result is not None
    assert result["year"] is None
