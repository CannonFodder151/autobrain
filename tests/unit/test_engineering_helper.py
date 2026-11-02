"""Unit tests for the VASS engineering helper state model."""

from backend.app.services.engineering_helper import (
    VehicleState,
    compute_guidance,
    primary_guidance,
    to_dict,
)


def _state(**kw):
    return VehicleState(vehicle_id="VIN1", **kw)


def test_engine_light_off_clean():
    g = compute_guidance(_state())
    engine = [x for x in g if x.state == "engine_light"][0]
    assert engine.severity == "info"
    assert engine.title == "Engine OK"


def test_engine_light_on_critical():
    g = compute_guidance(_state(engine_light_on=True, fault_codes=["P0301"]))
    engine = [x for x in g if x.state == "engine_light"][0]
    assert engine.severity == "critical"
    assert "P0301" in engine.message
    assert "Book a diagnostic scan" in engine.actions


def test_rego_valid_info():
    g = compute_guidance(_state(rego_valid=True, rego_expiry="2026-12-01"))
    r = [x for x in g if x.state == "rego"][0]
    assert r.severity == "info"
    assert "valid" in r.message


def test_rego_invalid_critical():
    g = compute_guidance(_state(rego_valid=False, rego_expiry="2026-01-01"))
    r = [x for x in g if x.state == "rego"][0]
    assert r.severity == "critical"
    assert "Renew registration" in r.actions


def test_service_overdue_warning():
    g = compute_guidance(_state(current_mileage=20000, last_service_mileage=10000, service_interval_km=5000))
    s = [x for x in g if x.state == "service_interval"][0]
    assert s.severity == "warning"
    assert "overdue" in s.message.lower()


def test_service_due_soon_info():
    g = compute_guidance(_state(current_mileage=9500, last_service_mileage=0, service_interval_km=10000))
    s = [x for x in g if x.state == "service_interval"][0]
    assert s.severity == "info"
    assert "due in" in s.message.lower()


def test_service_on_track():
    g = compute_guidance(_state(current_mileage=5000, last_service_mileage=0, service_interval_km=10000))
    s = [x for x in g if x.state == "service_interval"][0]
    assert s.severity == "info"
    assert "on track" in s.message.lower()


def test_ownership_ok():
    g = compute_guidance(_state(ownership_status="registered"))
    o = [x for x in g if x.state == "ownership"][0]
    assert o.severity == "info"


def test_ownership_pending_warning():
    g = compute_guidance(_state(ownership_status="transferring"))
    o = [x for x in g if x.state == "ownership"][0]
    assert o.severity == "warning"


def test_fuel_low_warning():
    g = compute_guidance(_state(fuel_level_pct=10.0))
    f = [x for x in g if x.state == "fuel"][0]
    assert f.severity == "warning"
    assert "Refuel" in f.actions


def test_fuel_ok():
    g = compute_guidance(_state(fuel_level_pct=60.0))
    f = [x for x in g if x.state == "fuel"][0]
    assert f.severity == "info"


def test_ev_battery_low_warning():
    g = compute_guidance(_state(is_ev=True, battery_soh_pct=60.0, range_km=120))
    e = [x for x in g if x.state == "ev_powertrain"][0]
    assert e.severity == "warning"
    assert "battery" in e.message.lower()


def test_ev_battery_ok():
    g = compute_guidance(_state(is_ev=True, battery_soh_pct=85.0, range_km=200))
    e = [x for x in g if x.state == "ev_powertrain"][0]
    assert e.severity == "info"


def test_phev_powertrain():
    g = compute_guidance(_state(is_phev=True, battery_soh_pct=75.0))
    e = [x for x in g if x.state == "ev_powertrain"][0]
    assert "PHEV" in e.message


def test_ic_powertrain_not_applicable():
    g = compute_guidance(_state(is_ev=False, is_phev=False))
    e = [x for x in g if x.state == "ev_powertrain"][0]
    assert e.severity == "info"
    assert "not applicable" in e.message.lower()


def test_primary_guidance_picks_critical():
    g = compute_guidance(_state(rego_valid=False, engine_light_on=True))
    p = primary_guidance(g)
    assert p.severity == "critical"


def test_primary_picks_warning_when_no_critical():
    g = compute_guidance(_state(fuel_level_pct=5.0))
    p = primary_guidance(g)
    assert p.severity == "warning"


def test_to_dict_serializable():
    g = compute_guidance(_state())[0]
    d = to_dict(g)
    assert set(d.keys()) == {"state", "severity", "title", "message", "actions"}


def test_unknown_mileage_service_info():
    g = compute_guidance(_state())
    s = [x for x in g if x.state == "service_interval"][0]
    assert s.severity == "info"


def test_ev_battery_low_service_overdue_ownership_pending():
    g = compute_guidance(
        _state(
            is_ev=True,
            battery_soh_pct=60.0,
            current_mileage=20000,
            last_service_mileage=10000,
            service_interval_km=5000,
            ownership_status="transferring",
        )
    )
    ev = [x for x in g if x.state == "ev_powertrain"][0]
    service = [x for x in g if x.state == "service_interval"][0]
    ownership = [x for x in g if x.state == "ownership"][0]
    rego = [x for x in g if x.state == "rego"][0]
    engine = [x for x in g if x.state == "engine_light"][0]
    fuel = [x for x in g if x.state == "fuel"][0]

    assert ev.severity == "warning"
    assert service.severity == "warning"
    assert ownership.severity == "warning"
    assert rego.severity == "info"
    assert engine.severity == "info"
    assert fuel.severity == "info"
    p = primary_guidance(g)
    assert p.severity == "warning"


def test_phev_low_fuel_rego_valid_service_due_soon():
    g = compute_guidance(
        _state(
            is_phev=True,
            battery_soh_pct=75.0,
            fuel_level_pct=10.0,
            rego_valid=True,
            rego_expiry="2026-12-01",
            current_mileage=9500,
            last_service_mileage=0,
            service_interval_km=10000,
        )
    )
    ev = [x for x in g if x.state == "ev_powertrain"][0]
    fuel = [x for x in g if x.state == "fuel"][0]
    rego = [x for x in g if x.state == "rego"][0]
    service = [x for x in g if x.state == "service_interval"][0]
    engine = [x for x in g if x.state == "engine_light"][0]
    ownership = [x for x in g if x.state == "ownership"][0]

    assert ev.severity == "info"
    assert fuel.severity == "warning"
    assert rego.severity == "info"
    assert service.severity == "info"
    assert engine.severity == "info"
    assert ownership.severity == "info"
    p = primary_guidance(g)
    assert p.severity == "warning"
    assert p.state == "fuel"


def test_ice_engine_light_rego_expired_fuel_low_service_overdue():
    g = compute_guidance(
        _state(
            is_ev=False,
            is_phev=False,
            engine_light_on=True,
            fault_codes=["P0300"],
            rego_valid=False,
            rego_expiry="2026-01-01",
            fuel_level_pct=5.0,
            current_mileage=25000,
            last_service_mileage=10000,
            service_interval_km=10000,
        )
    )
    engine = [x for x in g if x.state == "engine_light"][0]
    rego = [x for x in g if x.state == "rego"][0]
    fuel = [x for x in g if x.state == "fuel"][0]
    service = [x for x in g if x.state == "service_interval"][0]
    ev = [x for x in g if x.state == "ev_powertrain"][0]
    ownership = [x for x in g if x.state == "ownership"][0]

    assert engine.severity == "critical"
    assert rego.severity == "critical"
    assert fuel.severity == "warning"
    assert service.severity == "warning"
    assert ev.severity == "info"
    assert ownership.severity == "info"
    p = primary_guidance(g)
    assert p.severity == "critical"
    assert p.state in {"engine_light", "rego"}