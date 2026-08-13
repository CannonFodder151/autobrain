"""Billing (Stripe) tests: tier mapping, promote/demote, signup gating."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
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


class _FakeStripe:
    """Minimal Stripe client stub recording checkout params."""

    def __init__(self) -> None:
        self.created = None
        self.session_url = "https://checkout.stripe.test/sess"

    @property
    def customers(self):
        class _Customers:
            def list(self, **kw):
                return type("R", (), {"data": []})()

            def create(self, **kw):
                return type("C", (), {"id": "cus_1"})()

        return _Customers()

    @property
    def checkout(self):
        class _Sessions:
            def __init__(self, fake):
                self.fake = fake

            def create(self, params=None, **kw):
                self.fake.created = params
                return type("S", (), {"url": self.fake.session_url})()

        return type("C", (), {"sessions": _Sessions(self)})()


@pytest.fixture()
def sale(monkeypatch, stripe_prices):
    monkeypatch.setattr(settings, "STRIPE_PROMO_EARLY_ADOPTER", "promo_early40")
    monkeypatch.setattr(settings, "STRIPE_PROMO_EARLY_ADOPTER_CODE", "EARLY40")
    monkeypatch.setattr(settings, "STRIPE_SALE_ENDS_AT", "2999-01-01")
    return True


@pytest.fixture()
def fake_stripe(monkeypatch):
    fake = _FakeStripe()
    monkeypatch.setattr(svc, "get_client", lambda: fake)
    return fake


async def _checkout(fake: _FakeStripe, plan="enthusiast", billing="monthly", promo=None):
    await svc.create_checkout_session(
        None,
        _user(free_account=True, stripe_customer_id="cus_1"),
        plan,
        billing,
        promo,
    )
    return fake.created


def test_pricing_matches_approved_plan(sale) -> None:
    data = svc.pricing()
    assert data["currency"] == "aud"
    assert data["sale"]["active"] is True
    assert data["sale"]["code"] == "EARLY40"
    assert data["sale"]["percent_off"] == 40
    assert data["sale"]["cap"] == 100
    by_key = {p["key"]: p for p in data["plans"]}
    assert by_key["enthusiast"]["monthly"] == 900
    assert by_key["enthusiast"]["yearly"] == 8400
    assert by_key["enthusiast"]["sale_monthly"] == 540
    assert by_key["garage"]["monthly"] == 1900
    assert by_key["garage"]["yearly"] == 16800
    assert by_key["garage"]["sale_monthly"] == 1140


def test_pricing_no_sale_when_unconfigured(stripe_prices) -> None:
    data = svc.pricing()
    assert data["sale"]["active"] is False
    assert "sale_monthly" not in data["plans"][0]


@pytest.mark.asyncio
async def test_checkout_auto_applies_sale_on_monthly(sale, fake_stripe) -> None:
    params = await _checkout(fake_stripe)
    assert params["discounts"] == [{"promotion_code": "promo_early40"}]
    assert "allow_promotion_codes" not in params


@pytest.mark.asyncio
async def test_checkout_yearly_no_auto_discount(sale, fake_stripe) -> None:
    params = await _checkout(fake_stripe, billing="yearly")
    assert "discounts" not in params
    assert params["allow_promotion_codes"] is True


@pytest.mark.asyncio
async def test_checkout_explicit_promo_code(sale, fake_stripe) -> None:
    params = await _checkout(fake_stripe, promo="early40")
    assert params["discounts"] == [{"promotion_code": "promo_early40"}]


@pytest.mark.asyncio
async def test_checkout_unknown_promo_rejected(sale, fake_stripe) -> None:
    with pytest.raises(ValueError):
        await _checkout(fake_stripe, promo="NOPE")


@pytest.mark.asyncio
async def test_checkout_no_promo_configured_allows_codes(stripe_prices, fake_stripe) -> None:
    params = await _checkout(fake_stripe)
    assert "discounts" not in params
    assert params["allow_promotion_codes"] is True


@pytest.mark.asyncio
async def test_pricing_endpoint_public() -> None:
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/billing/pricing")
    assert resp.status_code == 200
    body = resp.json()
    assert {p["key"] for p in body["plans"]} == {"enthusiast", "garage"}
    assert "sale" in body
