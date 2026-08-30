"""AUT-324: rego provider logs must never contain raw payloads (PII)."""

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./t.db")
os.environ.setdefault("SECRET_KEY", "test-secret")

import pytest  # noqa: E402
from structlog.testing import capture_logs  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.services import rego as rego_svc  # noqa: E402


class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.status_code = 200

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, resp: _FakeResp) -> None:
        self._resp = resp

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def post(self, *args, **kwargs) -> _FakeResp:
        return self._resp


@pytest.mark.asyncio
async def test_rego_provider_log_never_contains_raw_payload(monkeypatch) -> None:
    payload = {
        "vehicle": {
            "registration_number": "3B4PV",
            "make": "Honda",
            "model": "CBR500R",
            "year": 2021,
            "vin": "JH2PC50A0MK000000",
            "owner_name": "Jane Doe",
            "address": "1 Smith St Sydney NSW 2000",
        }
    }
    monkeypatch.setattr(settings, "REGO_LOOKUP_URL", "http://rego.test/lookup")
    monkeypatch.setattr(settings, "REGO_LOOKUP_API_KEY", "k")
    monkeypatch.setattr(rego_svc.httpx, "AsyncClient", lambda **k: _FakeClient(_FakeResp(payload)))

    with capture_logs() as logs:
        result = await rego_svc.lookup_rego("3B4PV", state="NSW")

    assert result is not None
    assert result["make"] == "Honda"
    assert result["model"] == "CBR500R"
    text = str(logs)
    assert "JH2PC50A0MK000000" not in text
    assert "Jane Doe" not in text
    assert "1 Smith St" not in text
    assert "rego_provider_lookup" in text
