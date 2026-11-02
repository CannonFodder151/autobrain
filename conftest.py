import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
for p in (str(ROOT), str(BACKEND)):
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture(autouse=True)
def _reset_global_rate_limiter():
    from app.core.middleware import limiter
    limiter._counts.clear()
    yield


@pytest.fixture(autouse=True)
def _reset_demo_rate_limits():
    from app.services.demo_request import _ip_hits, _email_hits
    _ip_hits.clear()
    _email_hits.clear()
    yield


@pytest.fixture(autouse=True)
def _reset_track_state():
    from app.api.v1 import track
    track._CARS.clear()
    track._SESSIONS.clear()
    track._LAPS.clear()
    track._PREP.clear()
    track._SERVICE.clear()
    yield