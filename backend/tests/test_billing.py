"""Billing (Stripe) tests: tier mapping, promote/demote, signup gating."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://autobrain:autobrain@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import uuid  # noqa: E402

import pytest  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import billing as svc  # noqa: E402

_PRICES = {
    "STRIPE_PRICE_ENTHUSIAST_MONTHLY": "price_enth_m",
    "STRIPE_PRICE_ENTHUSIAST_YEARLY": "price_enth_y",
    "STRIPE_PRICE_GARAGE_MONTHLY": "price_gar_m",
    "STRIPE_PRICE_GARAGE_YEARLY": "price_gar_y",
}


def _user(**kw) -> User:
    defaults = dict(
        id=str(uuid.uuid4()),
        email="u@example.com",
        display_name="U",
        hashed_password="x",
        role="user",
        max_vehicles=1,
        free_account=True,
    )
    defaults.update(kw)
    return User(**defaults)


@pytest.fixture()
def stripe_prices(monkeypatch):
    for name, value in _PRICES.items():
        monkeypatch.setattr(settings, name, value)
    return _PRICES


def _subscribe(user: User, status: str, price: str) -> None:
    user.stripe_subscription_id = "sub_1"
    user.stripe_customer_id = "cus_1"
    user.stripe_subscription_status = status
    user.stripe_price_id = price
    # Mirror the webhook: active/trialing subscriptions grant the plan; anything
    # else demotes to the free tier.
    plan = svc.plan_for_price(price) if price else None
    if status in svc.ACTIVE_STATUSES and plan:
        svc.apply_plan(user, plan)
    else:
        svc.apply_free(user)


def test_price_lookup(stripe_prices) -> None:
    assert svc.price_for("enthusiast", "monthly") == "price_enth_m"
    assert svc.price_for("enthusiast", "yearly") == "price_enth_y"
    assert svc.price_for("garage", "monthly") == "price_gar_m"
    assert svc.price_for("garage", "yearly") == "price_gar_y"
    assert svc.price_for("club", "monthly") is None
    assert svc.plan_for_price("price_gar_y") == "garage"
    assert svc.plan_for_price("price_unknown") is None


def test_apply_plan_promotes_and_demotes(stripe_prices) -> None:
    u = _user()
    svc.apply_plan(u, "garage")
    assert u.free_account is False
    assert u.max_vehicles == 5
    svc.apply_free(u)
    assert u.free_account is True
    assert u.max_vehicles == 1


def test_plan_for_user(stripe_prices) -> None:
    active = _user()
    _subscribe(active, "active", "price_enth_m")
    assert svc.plan_for_user(active) == "enthusiast"

    trialing = _user()
    _subscribe(trialing, "trialing", "price_gar_y")
    assert svc.plan_for_user(trialing) == "garage"

    canceled = _user()
    _subscribe(canceled, "canceled", "price_gar_m")
    assert svc.plan_for_user(canceled) == "free"

    free = _user(free_account=True)
    assert svc.plan_for_user(free) == "free"

    # Admin-granted access without a Stripe subscription is not a paid plan.
    admin_granted = _user(free_account=False, max_vehicles=10)
    assert svc.plan_for_user(admin_granted) == "free"
    assert svc.has_paid_subscription(admin_granted) is False


@pytest.mark.asyncio
async def test_checkout_unknown_plan(stripe_prices) -> None:
    with pytest.raises(ValueError):
        await svc.create_checkout_session(None, _user(), "club", "monthly")


@pytest.mark.asyncio
async def test_webhook_rejects_missing_secret(monkeypatch) -> None:
    monkeypatch.setattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    with pytest.raises(RuntimeError):
        svc.construct_event(b"{}", "sig")


@pytest.mark.asyncio
async def test_public_signup_disabled_by_default() -> None:
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": "new@example.com",
                "display_name": "New User",
            },
        )
    assert resp.status_code == 403
    assert "disabled" in resp.json()["detail"].lower()
