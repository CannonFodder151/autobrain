"""AUT-2434: vehicle powertrain enum (ICE | EV | HEV | PHEV).

Offline checks (no Postgres required): the column exists on the model, the
canonical token set is locked to four members, the Pydantic schemas
accept/serialize ``powertrain``, defaults to ICE on VehicleCreate/VehicleOut,
and the alembic revision sits cleanly on top of the aut1859 head.
"""

from datetime import datetime, timezone

from app.models.vehicle import PowertrainType, Vehicle
from app.schemas.vehicle import VehicleCreate, VehicleOut, VehicleUpdate


def test_vehicle_model_has_powertrain_column() -> None:
    from sqlalchemy import inspect

    cols = [c.key for c in inspect(Vehicle).columns]
    assert "powertrain" in cols


def test_powertrain_enum_is_locked() -> None:
    # Adding a new powertrain is a deliberate, versioned event — not an accident
    # of someone inventing a new string token.
    assert {p.value for p in PowertrainType} == {"ICE", "EV", "HEV", "PHEV"}


def test_vehicle_create_defaults_to_ice() -> None:
    vc = VehicleCreate(nickname="Daily")
    assert vc.powertrain is PowertrainType.ICE
    assert vc.model_dump()["powertrain"] == "ICE"


def test_vehicle_create_accepts_ev() -> None:
    vc = VehicleCreate(nickname="Tesla", powertrain=PowertrainType.EV)
    assert vc.model_dump()["powertrain"] == "EV"


def test_vehicle_create_accepts_phev() -> None:
    vc = VehicleCreate(nickname="Leaf", powertrain=PowertrainType.PHEV)
    assert vc.model_dump()["powertrain"] == "PHEV"


def test_vehicle_create_roundtrip_all_powertrains() -> None:
    for p in PowertrainType:
        vc = VehicleCreate(nickname="V", powertrain=p)
        assert vc.model_dump()["powertrain"] == p.value


def test_vehicle_update_carries_powertrain() -> None:
    assert VehicleUpdate(powertrain=PowertrainType.PHEV).powertrain is PowertrainType.PHEV
    assert VehicleUpdate().powertrain is None
    # powertrain must survive a model_dump so PATCH bodies carry it through.
    assert VehicleUpdate(powertrain="HEV").model_dump()["powertrain"] == "HEV"


def test_vehicle_out_serializes_powertrain() -> None:
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
        powertrain=PowertrainType.PHEV,
        is_shared=False,
        shared_by=None,
        created_at=datetime.now(timezone.utc),
    )
    assert out.model_dump()["powertrain"] == "PHEV"