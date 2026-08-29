"""AUT-1884: shared-vehicle fuel-up save + receipt OCR resilience.

Three reported symptoms:
  (A) "added a fuel up — it loaded then did not save" on a SHARED vehicle.
      Root cause: `add_fuel` commits the row, then fires a best-effort
      background due-notification via Celery. When the broker (Redis) is
      momentarily down, the dispatch raised AFTER commit and surfaced a 500 to
      the client — the row persisted but the app read it as a failed save.
      Fix: dispatch is now fire-and-forget and never masks a committed write.
  (B) "receipt OCR did not work" — the upload endpoint gated the ENTIRE
      operation (including deterministic photo storage) behind the AI rate
      limiter, which fails closed to 503 when Redis is down. Fix: the limiter
      is now best-effort (fail-open) for the storage/OCR path; 9Router
      enrichment still falls back to the deterministic baseline.
  (C) "camera did not open — it opened my files library" — frontend fix
      (image_picker camera + file chooser). Tested in the Flutter suite.

Requires the compose Postgres + MinIO (same as the rest of the suite).
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import uuid  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.vehicle import Vehicle  # noqa: E402


async def _create_user(db, email: str, free: bool = False) -> User:
    user = User(
        email=email,
        display_name=email,
        hashed_password=hash_password("hunter22"),
        max_vehicles=3,
        free_account=free,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _world() -> dict:
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        owner = await _create_user(db, f"own-{suffix}@example.com", free=False)
        invitee = await _create_user(db, f"inv-{suffix}@example.com", free=True)
        vehicle = Vehicle(user_id=owner.id, nickname="Shared Whip", rego="TOY123")
        db.add(vehicle)
        await db.commit()
        await db.refresh(vehicle)
        owner_token = create_access_token(owner.id)
        invitee_token = create_access_token(invitee.id)
        vehicle_id = vehicle.id
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    resp = await client.post(
        f"/api/v1/vehicles/{vehicle_id}/shares",
        json={"email": f"inv-{suffix}@example.com"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert resp.status_code == 201, resp.text
    share_id = resp.json()["id"]
    resp = await client.post(
        f"/api/v1/vehicle-shares/{share_id}/accept",
        headers={"Authorization": f"Bearer {invitee_token}"},
    )
    assert resp.status_code == 200, resp.text
    return {
        "client": client,
        "invitee_token": invitee_token,
        "vehicle_id": vehicle_id,
    }


@pytest.mark.asyncio
async def test_shared_invitee_fuel_save_survives_notification_dispatch_failure() -> None:
    """(A) A shared invitee's fuel-up must persist even when the due-notification
    Celery task dispatch blows up — the committed row must not be masked by a 500."""
    import app.workers.tasks as tasks

    class _BoomTask:
        def delay(self, *a, **k):
            raise RuntimeError("broker down")

    original = tasks.check_due_notifications
    tasks.check_due_notifications = _BoomTask()  # type: ignore[assignment]
    try:
        world = await _world()
        c = world["client"]
        vid = world["vehicle_id"]
        ih = {"Authorization": f"Bearer {world['invitee_token']}"}

        body = {
            "fill_date": "2026-08-28",
            "odometer_km": 12000,
            "litres": 45.0,
            "price_per_litre": 2.1,
            "is_full_tank": True,
        }
        resp = await c.post(f"/api/v1/vehicles/{vid}/fuel", json=body, headers=ih)
        assert resp.status_code == 201, resp.text

        logs = (await c.get(f"/api/v1/vehicles/{vid}/fuel", headers=ih)).json()
        assert len(logs) == 1, logs
        assert logs[0]["litres"] == 45.0
    finally:
        tasks.check_due_notifications = original  # type: ignore[assignment]
        await world["client"].aclose()


@pytest.mark.asyncio
async def test_fuel_receipt_upload_survives_rate_limiter_outage() -> None:
    """(B) Receipt photo storage must succeed even when the AI rate limiter's
    Redis is unreachable (fail-open), so a blip never drops the upload."""
    import app.services.rate_limit as rl

    async def _raise(*a, **k):
        raise RuntimeError("redis down")

    original = rl._bump
    rl._bump = _raise  # type: ignore[assignment]
    try:
        world = await _world()
        c = world["client"]
        vid = world["vehicle_id"]
        ih = {"Authorization": f"Bearer {world['invitee_token']}"}

        # Minimal valid PNG (storage path runs; OCR enrichment just falls back).
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x08\x00\x00\x00\x08"
            b"\x08\x06\x00\x00\x00\x8e\xeb}\xce"
        )
        resp = await c.post(
            f"/api/v1/vehicles/{vid}/fuel/receipt?ai=true",
            headers=ih,
            files={"file": ("receipt.png", png, "image/png")},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json().get("receipt_id")
    finally:
        rl._bump = original  # type: ignore[assignment]
        await world["client"].aclose()
