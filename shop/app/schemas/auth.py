"""Auth schemas for AutoBrain Shop."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class WorkshopUserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="tech", pattern="^(owner|manager|tech|admin)$")


class WorkshopUserLogin(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = Field(default=None, max_length=10)


class WorkshopCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=100, pattern="^[a-z0-9-]+$")
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=50)
    postcode: str | None = Field(default=None, max_length=20)
    country: str = Field(default="AU", pattern="^[A-Z]{2}$")
    abn: str | None = Field(default=None, max_length=20)
    subscription_tier: str = Field(default="starter", pattern="^(starter|professional|enterprise)$")


class WorkshopUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=50)
    postcode: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, pattern="^[A-Z]{2}$")
    abn: str | None = Field(default=None, max_length=20)
    subscription_tier: str | None = Field(default=None, pattern="^(starter|professional|enterprise)$")
    max_users: int | None = Field(default=None, ge=1, le=1000)
    max_vehicles: int | None = Field(default=None, ge=1, le=10000)
    ai_enabled: bool | None = None
    is_active: bool | None = None


class WorkshopUserOut(BaseModel):
    id: str
    workshop_id: str
    email: EmailStr
    display_name: str
    role: str
    is_active: bool
    mfa_enabled: bool
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkshopOut(BaseModel):
    id: str
    name: str
    slug: str
    email: EmailStr
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    postcode: str | None = None
    country: str
    abn: str | None = None
    subscription_tier: str
    subscription_status: str
    max_users: int
    max_vehicles: int
    ai_enabled: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkshopPage(BaseModel):
    items: list[WorkshopOut]
    total: int
    page: int
    pages: int

    model_config = {"from_attributes": True}


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: WorkshopUserOut


class LoginResult(BaseModel):
    token_pair: TokenPair | None = None
    mfa_required: bool = False
    mfa_token: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    code: str = Field(min_length=6, max_length=10)


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_url: str
    qr_data_url: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)