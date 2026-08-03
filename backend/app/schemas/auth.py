"""Auth schemas."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="user", pattern="^(admin|user)$")


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = Field(default=None, max_length=10)


class UserOut(BaseModel):
    id: str
    email: EmailStr
    display_name: str
    role: str
    is_active: bool
    mfa_enabled: bool

    model_config = {"from_attributes": True}


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class MfaRequired(BaseModel):
    mfa_required: bool = True
    mfa_token: str


class LoginResult(BaseModel):
    token_pair: TokenPair | None = None
    mfa_required: bool = False
    mfa_token: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    code: str = Field(min_length=6, max_length=10)


class MfaCodeRequest(BaseModel):
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


# --- Admin user management ---
class AdminUserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, pattern="^(admin|user)$")
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserAdminOut(BaseModel):
    id: str
    email: EmailStr
    display_name: str
    role: str
    is_active: bool
    mfa_enabled: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
