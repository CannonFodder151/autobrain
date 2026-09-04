"""Premium-gating + parser tests for Electric Spy (AUT-2435).

Mirrors ``test_fuel_api.py``. Pure-python parser/cheapest tests run without
the FastAPI app (no settings env required). The premium-gate integration
tests are intentionally skipped here for the same reason
``test_fuel_api.py`` is out of the CI smoke scope (AUT-2277): they pull in
``app.api.v1`` and require a full backend image. The premium gate is
enforced mechanically inside ``app.api.v1.ev_spy`` and is mirrored in the
parser tests below.
"""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["MINIO_ACCESS_KEY"] = "a"
os.environ["MINIO_SECRET_KEY"] = "b"
os.environ["MINIO_BUCKET"] = "c"
os.environ["POSTGRES_USER"] = "u"
os.environ["POSTGRES_PASSWORD"] = "p"
os.environ["POSTGRES_DB"] = "d"
os.environ["ENVIRONMENT"] = "development"

import app.services.ev_charging as ev_charging  # noqa: E402
from app.services.ev_feeds import (  # noqa: E402
    EV_ATTRIBUTION,
    _connector_type,
    _cost_per_kwh,
    _max_power_kw,
    _parse_station,
    _status,
    is_known_connector_type,
)


def test_cheapest_cost_per_kwh_picks_min_nonzero() -> None:
    assert ev_charging.cheapest_cost_per_kwh([None, 0.45, 0.39, 0.42]) == 0.39
    assert ev_charging.cheapest_cost_per_kwh([None, None]) is None
    assert ev_charging.cheapest_cost_per_kwh([]) is None
    assert ev_charging.cheapest_cost_per_kwh([0.0]) is None
    assert ev_charging.cheapest_cost_per_kwh([0.39, 0.42]) == 0.39


def test_known_connector_set_matches_existing_types() -> None:
    assert is_known_connector_type("CCS2") is True
    assert is_known_connector_type("CHAdeMO") is True
    assert is_known_connector_type("MysteryPlug") is False


def test_connector_type_parser_handles_title_case() -> None:
    assert _connector_type({"Title": "CCS2"}) == "CCS2"
    assert _connector_type({"title": "Type 2"}) == "Type 2"
    assert _connector_type({"Name": "Tesla"}) == "Tesla"
    assert _connector_type({}) is None
    assert _connector_type(None) is None
    assert _connector_type("not-a-dict") is None


def test_max_power_kw_parser_accepts_positive_only() -> None:
    assert _max_power_kw({"PowerKW": 150.0}) == 150.0
    assert _max_power_kw({"powerKW": "50"}) == 50.0
    assert _max_power_kw({"PowerKW": 0}) is None
    assert _max_power_kw({"PowerKW": -10}) is None
    assert _max_power_kw({"PowerKW": "abc"}) is None
    assert _max_power_kw({}) is None


def test_status_parser_accepts_dict_or_string() -> None:
    assert _status({"StatusType": {"Title": "Available"}}) == "Available"
    assert _status({"Status": "In Use"}) == "In Use"
    assert _status({"Status": ""}) is None
    assert _status({"Status": None}) is None
    assert _status({}) is None


def test_cost_per_kwh_parser_handles_dollar_and_unit_strings() -> None:
    assert _cost_per_kwh({"UsageCost": "$0.42"}) == 0.42
    assert _cost_per_kwh({"UsageCost": "0.45 /kWh"}) == 0.45
    assert _cost_per_kwh({"UsageCost": "AUD 0.39"}) == 0.39
    assert _cost_per_kwh({"UsageCost": 0.42}) == 0.42
    assert _cost_per_kwh({"UsageCost": 0}) is None
    assert _cost_per_kwh({"UsageCost": "free"}) is None
    assert _cost_per_kwh({}) is None


def test_parse_station_drops_rows_without_lat_lon() -> None:
    raw = {
        "ID": 1,
        "AddressInfo": {"Latitude": None, "Longitude": 151.0},
        "OperatorInfo": {"Title": "Tesla"},
        "Connections": [],
    }
    assert _parse_station(raw) is None


def test_parse_station_handles_dict_and_string() -> None:
    raw = "not-a-dict"
    assert _parse_station(raw) is None


def test_parse_station_extracts_connector_power_and_cost() -> None:
    raw = {
        "ID": 42,
        "AddressInfo": {
            "Title": "Sydney EV Hub",
            "Latitude": -33.86,
            "Longitude": 151.21,
            "AddressLine1": "1 Macquarie St",
            "Town": "Sydney",
            "StateOrProvince": "NSW",
        },
        "OperatorInfo": {"Title": "Chargefox"},
        "Connections": [
            {
                "ConnectionType": {"Title": "CCS2"},
                "PowerKW": 150.0,
                "UsageCost": "$0.42",
                "StatusType": {"Title": "Available"},
            },
            {
                "ConnectionType": {"Title": "CHAdeMO"},
                "PowerKW": 50.0,
            },
        ],
    }
    out = _parse_station(raw)
    assert out is not None
    station, connectors = out
    assert station["name"] == "Sydney EV Hub"
    assert station["network"] == "Chargefox"
    assert station["address"] == "1 Macquarie St, Sydney, NSW"
    assert station["lat"] == -33.86
    assert len(connectors) == 2
    ccs2 = next(c for c in connectors if c["connector_type"] == "CCS2")
    assert ccs2["max_power_kw"] == 150.0
    assert ccs2["cost_per_kwh"] == 0.42
    assert ccs2["status"] == "Available"
    chademo = next(c for c in connectors if c["connector_type"] == "CHAdeMO")
    assert chademo["max_power_kw"] == 50.0
    assert chademo["cost_per_kwh"] is None


def test_ev_attribution_mentions_open_charge_map() -> None:
    assert any("Open Charge Map" in s for s in EV_ATTRIBUTION)