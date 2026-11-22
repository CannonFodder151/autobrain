"""AUT-731 — Electric Spy charging price watch alerts (pure logic tests).

Covers the deterministic price-comparison decisioning and the
watchlist notify endpoint route registration. No Postgres / Redis /
network required, so the guard logic is verifiable in CI without a
DB provision.
"""

from app.services.charging_servo import should_alert_charging_price
from app.api.v1.charging import router


# --- should_alert_charging_price (pure) ------------------------------------

def test_no_current_price_no_alert():
    should, reason = should_alert_charging_price(None, 45.0)
    assert should is False
    assert reason == "no_data"


def test_no_target_no_alert():
    should, reason = should_alert_charging_price(45.0, None)
    assert should is False
    assert reason == "no_data"


def test_price_at_target_triggers():
    should, reason = should_alert_charging_price(45.0, 45.0)
    assert should is True
    assert reason == "threshold_met"


def test_price_below_target_triggers():
    should, reason = should_alert_charging_price(40.0, 45.0)
    assert should is True
    assert reason == "threshold_met"


def test_price_above_target_no_alert():
    should, reason = should_alert_charging_price(50.0, 45.0)
    assert should is False
    assert reason == "above_target"


# --- Watchlist notify route registered ------------------------------------

def _route_paths() -> list[str]:
    return [getattr(r, "path", None) for r in router.routes]


def test_notify_route_registered():
    paths = _route_paths()
    assert "/charging/watchlist/notify" in paths