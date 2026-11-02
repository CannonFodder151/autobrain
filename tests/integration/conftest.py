import pytest


@pytest.fixture(autouse=True)
def _reset_track_state():
    print(">>> CONFTEST FIXTURE RUNNING <<<")
    from backend.app.api.v1 import track
    import backend.app.api.v1.track as track_mod2
    print(f"track is track_mod2: {track is track_mod2}")
    print(f"track._SESSIONS id: {id(track._SESSIONS)}")
    print(f"track_mod2._SESSIONS id: {id(track_mod2._SESSIONS)}")
    print(f"Before clear: _SESSIONS={len(track._SESSIONS)}")
    track._CARS.clear()
    track._SESSIONS.clear()
    track._LAPS.clear()
    track._PREP.clear()
    track._SERVICE.clear()
    print(f"After clear: _SESSIONS={len(track._SESSIONS)}")
    yield
    print(">>> CONFTEST FIXTURE TEARDOWN <<<")
