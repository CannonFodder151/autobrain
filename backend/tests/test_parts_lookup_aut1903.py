"""AUT-1903: parts lookup is driven by the selected vehicle's rego + state.

Offline-only: REGO_LOOKUP_URL and MARKET_DATA_URL are unset in the test env,
so the rego resolver runs its deterministic heuristic (prefix / word decode)
with no network. Proves the "use the vehicle's plate + state" path resolves a
vehicle deterministically, and that without a state the rego path can't fire
(honouring why the state must be stored per-vehicle).
"""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://autobrain:autobrain@localhost:5432/autobrain"
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("MARKET_DATA_URL", "")
os.environ.setdefault("MARKET_DATA_API_KEY", "")

import pytest  # noqa: E402

from app.services.parts_guide import lookup_vehicle  # noqa: E402


@pytest.mark.asyncio
async def test_lookup_vehicle_resolves_via_rego_and_state() -> None:
    """A plate + state resolves a vehicle through the deterministic heuristic."""
    hit = await lookup_vehicle(
        rego="TCRWN123", state="VIC", make="", model="", year=None
    )
    assert hit is not None
    # Word-decoded personalised plate "CRWN" -> Toyota Crown.
    assert hit["make"] == "Toyota"
    assert hit["model"] == "Crown"
    assert hit["state"] == "VIC"
    assert hit["rego"] == "TCRWN123"


@pytest.mark.asyncio
async def test_lookup_vehicle_without_state_falls_back_to_make_model() -> None:
    """No vehicle state => the rego path can't fire; uses stored make/model."""
    hit = await lookup_vehicle(
        rego="TCRWN123", state=None, make="Toyota", model="Crown", year=1997
    )
    assert hit is not None
    assert hit["make"] == "Toyota"
    assert hit["model"] == "Crown"
    assert hit["year"] == 1997
    assert hit["source"] == "user-input"
    assert hit["rego"] == "TCRWN123"
    assert hit.get("state") is None


@pytest.mark.asyncio
async def test_lookup_vehicle_invalid_plate_is_none_without_state() -> None:
    """Garbage rego without make/model yields None (no fabricated vehicle)."""
    hit = await lookup_vehicle(rego="!!!", state=None, make="", model="", year=None)
    assert hit is None
