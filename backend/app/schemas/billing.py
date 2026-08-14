"""Billing (Stripe + store IAP) request/response schemas."""

from pydantic import BaseModel, Field


class CheckoutRequest(BaseModel):
    plan: str = Field(pattern="^(enthusiast|garage)$")
    billing: str = Field(default="monthly", pattern="^(monthly|yearly)$")
    promo_code: str | None = None


class CheckoutResponse(BaseModel):
    url: str


class PortalResponse(BaseModel):
    url: str


class IapVerifyRequest(BaseModel):
    """Store transaction reported by the mobile app (AUT-610/617)."""

    platform: str = Field(pattern="^(android|ios)$")
    product_id: str = Field(min_length=1)
    transaction_id: str = Field(min_length=1)
    purchase_token: str = ""
    purchase_time_ms: int | None = None


class IapVerifyResponse(BaseModel):
    status: str
    plan: str
    max_vehicles: int
    free_account: bool
