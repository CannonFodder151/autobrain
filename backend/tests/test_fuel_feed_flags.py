"""Fuel-feed enable flags must match what is actually wired.

AUT-4976: VIC Servo Saver is disabled everywhere — api.servosaver.com.au is
NXDOMAIN (AUT-4143), so an enabled VIC feed only added a FuelFeedError to every
nightly beat.
AUT-5072: SA SAFPIS is disabled everywhere — the Informed Sources Direct API
host (fppdirectapi.safuelpricinginformation.com.au) is NXDOMAIN *and* no
``ingest_sa_*`` function exists, so ``FUEL_SA_ENABLED: "true"`` was dead config
that silently produced zero stations forever.

The flags must not drift back on until a contracted aggregator exists, and no
feed may be enabled without a parser wired into ``ingest_all_fuel``.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = ["docker-compose.hosted.yml", "docker-compose.prod.yml"]
FEEDS_PY = REPO_ROOT / "backend/app/services/fuel_feeds.py"


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_vic_fuel_feed_disabled(compose_file: str) -> None:
    text = (REPO_ROOT / compose_file).read_text()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("FUEL_VIC_ENABLED:")]
    assert lines, f"{compose_file} no longer declares FUEL_VIC_ENABLED"
    assert lines == ['FUEL_VIC_ENABLED: "false"'], lines


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_sa_fuel_feed_disabled(compose_file: str) -> None:
    text = (REPO_ROOT / compose_file).read_text()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("FUEL_SA_ENABLED:")]
    assert lines, f"{compose_file} no longer declares FUEL_SA_ENABLED"
    assert lines == ['FUEL_SA_ENABLED: "false"'], lines


def test_no_sa_feed_parser_wired() -> None:
    """There is no SA ingester, so /fuel/stations must not advertise SA coverage."""
    text = FEEDS_PY.read_text()
    assert "def ingest_sa" not in text, "SA ingester added — re-enable FUEL_SA_ENABLED + this doc"
    assert '"source": "sa"' not in text
    # Coverage on /fuel/stations is whatever is in `fuel_stations`; no hardcoded
    # state list may claim SA.
    servo = (REPO_ROOT / "backend/app/api/v1/fuel_servo.py").read_text()
    assert '"SA"' not in servo and "'SA'" not in servo
