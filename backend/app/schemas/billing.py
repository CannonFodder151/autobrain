"""Billing (Stripe) request/response schemas."""

from pydantic import BaseModel, Field


class CheckoutRequest(BaseModel):
    plan: str = Field(pattern="^(enthusiast|garage)$")
    billing: str = Field(default="monthly", pattern="^(monthly|yearly)$")
    promo_code: str | None = None


class CheckoutResponse(BaseModel):
    url: str


class PortalResponse(BaseModel):
    url: str
