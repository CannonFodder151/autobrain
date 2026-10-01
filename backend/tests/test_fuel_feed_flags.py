"""AUT-4976: VIC Servo Saver feed is disabled everywhere.

api.servosaver.com.au is NXDOMAIN (AUT-4143), so an enabled VIC feed only added a
FuelFeedError to every nightly beat. Guard the compose flag so it cannot drift
back on when a paid VIC aggregator replaces the dead endpoint.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = ["docker-compose.hosted.yml", "docker-compose.prod.yml"]


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_vic_fuel_feed_disabled(compose_file: str) -> None:
    text = (REPO_ROOT / compose_file).read_text()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("FUEL_VIC_ENABLED:")]
    assert lines, f"{compose_file} no longer declares FUEL_VIC_ENABLED"
    assert lines == ['FUEL_VIC_ENABLED: "false"'], lines