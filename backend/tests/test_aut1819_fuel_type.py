"""AUT-1819: vehicle fuel_type column, schema surface and dropdown fallback.

Offline checks (no Postgres required): the column exists on the model, the
Pydantic schemas accept/serialize ``fuel_type``, and the static fuel-type
fallback list matches the backend ``DEFAULT_FUEL_TYPES`` catalogue tokens.
"""

from datetime import datetime, timezone

from app.models.vehicle import Vehicle
from app.schemas.vehicle import VehicleOut, VehicleUpdate


def test_vehicle_model_has_fuel_type_column() -> None:
    from sqlalchemy import inspect

    cols = [c.key for c in inspect(Vehicle).columns]
    assert "fuel_type" in cols


def test_vehicle_update_accepts_fuel_type() -> None:
    assert VehicleUpdate(fuel_type="98").fuel_type == "98"
    assert VehicleUpdate().fuel_type is None
    # fuel_type must survive a model_dump so PATCH bodies carry it through.
    assert VehicleUpdate(fuel_type="Diesel").model_dump()["fuel_type"] == "Diesel"


def test_vehicle_out_serializes_fuel_type() -> None:
    out = VehicleOut(
        id="v1",
        nickname="The Whip",
        rego=None,
        rego_state=None,
        vin=None,
        make=None,
        model=None,
        colour=None,
        body_type=None,
        year=None,
        engine=None,
        transmission=None,
        odometer_km=None,
        condition="good",
        vehicle_type="car",
        is_primary=False,
        club_reg=False,
        auto_suggest_service=False,
        fuel_type="E10",
        is_shared=False,
        shared_by=None,
        created_at=datetime.now(timezone.utc),
    )
    assert out.model_dump()["fuel_type"] == "E10"
    assert VehicleOut(
        id="v2",
        nickname="n",
        rego=None,
        rego_state=None,
        vin=None,
        make=None,
        model=None,
        colour=None,
        body_type=None,
        year=None,
        engine=None,
        transmission=None,
        odometer_km=None,
        condition="good",
        vehicle_type="car",
        is_primary=False,
        club_reg=False,
        auto_suggest_service=False,
        is_shared=False,
        shared_by=None,
        created_at=datetime.now(timezone.utc),
    ).fuel_type is None


def test_fuel_type_catalogue_matches_backend_defaults() -> None:
    from app.services.fuel_feeds import DEFAULT_FUEL_TYPES

    # The frontend fallback list must stay in lock-step with the backend
    # catalogue so the dropdown options and persisted tokens agree.
    assert DEFAULT_FUEL_TYPES == ["E10", "91", "95", "98", "Diesel", "LPG"]
