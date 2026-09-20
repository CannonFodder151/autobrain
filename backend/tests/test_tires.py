"""Tests for tire inventory and usage tracking (AUT-3614)."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

from datetime import date

import pytest

from app.models.tire import (
    MIN_TREAD_MM,
    COMPOUND_LIFE_KM,
    COMPOUND_NEW_TREAD_MM,
    HEAT_CYCLE_PENALTY_PER_CYCLE,
    TireSet,
    TireSession,
    TireTreadReading,
)
from app.schemas.tire import TireSessionCreate, TireSetCreate, TireTreadReadingCreate


class TestTireSetProperties:

    def _make_tire_set(self, compound="street", new_tread=8.0, sessions=None, readings=None):
        ts = TireSet(
            id="test-1", vehicle_id="veh-1", name="Front Street Set",
            brand="Michelin", model="Pilot Sport 4S", size="245/40R18",
            compound=compound, new_tread_mm=new_tread, status="active",
        )
        ts.sessions = sessions or []
        ts.tread_readings = readings or []
        return ts

    def test_heat_cycles_from_session_count(self):
        sessions = [TireSession(session_date=date(2026,1,1), session_type="track") for _ in range(3)]
        ts = self._make_tire_set(sessions=sessions)
        assert ts.heat_cycles == 3
        assert ts.total_sessions == 3

    def test_heat_cycles_zero_sessions(self):
        assert self._make_tire_set().heat_cycles == 0

    def test_remaining_tread_mm_returns_latest(self):
        readings = [TireTreadReading(reading_date=date(2026,1,1), depth_mm=7.5),
                    TireTreadReading(reading_date=date(2026,3,1), depth_mm=6.0)]
        assert self._make_tire_set(readings=readings).remaining_tread_mm == 6.0

    def test_remaining_tread_mm_none_when_no_readings(self):
        assert self._make_tire_set().remaining_tread_mm is None

    def test_end_of_life_at_min_tread(self):
        readings = [TireTreadReading(reading_date=date(2026,1,1), depth_mm=MIN_TREAD_MM)]
        ts = self._make_tire_set(readings=readings)
        assert ts.is_end_of_life is True
        assert ts.predicted_remaining_km == 0.0

    def test_end_of_life_below_min_tread(self):
        readings = [TireTreadReading(reading_date=date(2026,1,1), depth_mm=1.0)]
        assert self._make_tire_set(readings=readings).is_end_of_life is True

    def test_predicted_remaining_km_full_life(self):
        ts = self._make_tire_set(compound="street", new_tread=8.0)
        assert ts.predicted_remaining_km == COMPOUND_LIFE_KM["street"]

    def test_predicted_remaining_km_with_tread_wear(self):
        readings = [TireTreadReading(reading_date=date(2026,1,1), depth_mm=4.0)]
        ts = self._make_tire_set(compound="street", new_tread=8.0, readings=readings)
        assert ts.predicted_remaining_km == COMPOUND_LIFE_KM["street"] * 0.5

    def test_predicted_remaining_km_with_heat_cycles(self):
        sessions = [TireSession(session_date=date(i, 1, 1)) for i in range(1, 11)]
        ts = self._make_tire_set(compound="track", sessions=sessions)
        expected_factor = max(0.1, 1.0 - 10 * HEAT_CYCLE_PENALTY_PER_CYCLE)
        expected = COMPOUND_LIFE_KM["track"] * expected_factor
        assert ts.predicted_remaining_km == expected

    def test_end_of_life_pct_calculation(self):
        readings = [TireTreadReading(reading_date=date(2026,1,1), depth_mm=4.0)]
        sessions = [TireSession(session_date=date(i, 1, 1)) for i in range(1, 6)]
        ts = self._make_tire_set(compound="street", new_tread=8.0, sessions=sessions, readings=readings)
        pct = ts.end_of_life_pct
        assert pct is not None and 0 < pct < 100

    def test_all_compounds_have_life_estimate(self):
        for c in ["street","all_season","performance","track","racing","rally","wet","drag"]:
            assert c in COMPOUND_LIFE_KM and COMPOUND_LIFE_KM[c] > 0
            assert c in COMPOUND_NEW_TREAD_MM and COMPOUND_NEW_TREAD_MM[c] > 0


class TestTireSchemas:

    def test_tire_set_create_valid(self):
        ts = TireSetCreate(name="Front Set", brand="Michelin", model="PS4S", size="245/40R18", compound="street")
        assert ts.name == "Front Set"
        assert ts.new_tread_mm == 8.0

    def test_tire_session_create_valid(self):
        s = TireSessionCreate(session_date=date(2026,6,1), track_name="Phillip Island", session_type="track", distance_km=120.0)
        assert s.track_name == "Phillip Island"
        assert s.distance_km == 120.0

    def test_tread_reading_create_valid(self):
        r = TireTreadReadingCreate(reading_date=date(2026,6,1), depth_mm=6.5)
        assert r.depth_mm == 6.5
