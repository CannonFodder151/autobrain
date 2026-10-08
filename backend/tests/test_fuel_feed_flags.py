"""Compose-flag guards for dead fuel feeds (AUT-4976, AUT-5072).

* VIC (AUT-4976): api.servosaver.com.au is NXDOMAIN (AUT-4143), so an
  enabled VIC feed only added a FuelFeedError to every nightly beat.
* SA (AUT-5072): the SAFPIS Direct API host
  (fppdirectapi.safuelpricinginformation.com.au, per the AUT-2372
  research doc) is NXDOMAIN and no subscriber token was ever contracted,
  so FUEL_SA_ENABLED was set to "true" with no ingest_sa_* function to
  consume it — nominally enabled, silently producing zero stations
  forever. Guard the flag so it cannot drift back on until an
  aggregator is contracted.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = ["docker-compose.hosted.yml", "docker-compose.prod.yml"]


def _flag_lines(text: str, flag: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip().startswith(f"{flag}:")]


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_vic_fuel_feed_disabled(compose_file: str) -> None:
    text = (REPO_ROOT / compose_file).read_text()
    lines = _flag_lines(text, "FUEL_VIC_ENABLED")
    assert lines, f"{compose_file} no longer declares FUEL_VIC_ENABLED"
    assert lines == ['FUEL_VIC_ENABLED: "false"'], lines


@pytest.mark.parametrize("compose_file", COMPOSE_FILES)
def test_sa_fuel_feed_disabled(compose_file: str) -> None:
    text = (REPO_ROOT / compose_file).read_text()
    lines = _flag_lines(text, "FUEL_SA_ENABLED")
    assert lines, f"{compose_file} no longer declares FUEL_SA_ENABLED"
    assert lines == ['FUEL_SA_ENABLED: "false"'], lines
