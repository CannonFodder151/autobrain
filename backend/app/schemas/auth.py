"""Auth schemas."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: str = Field(default="user", pattern="^(admin|user)$")
    max_vehicles: int = Field(default=1, ge=1, le=1000)
    send_invite: bool = False  # email a create-account link instead of setting a password
    free_account: bool = False
    obd_enabled: bool = False


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = Field(default=None, max_length=10)


class SignupRequest(BaseModel):
    """Self-service signup (hosted Free tier). No password — the user receives
    an email with a setup link to choose a password + MFA."""

    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)


class UserOut(BaseModel):
    id: str
    email: EmailStr
    display_name: str
    role: str
    is_active: bool
    mfa_enabled: bool
    max_vehicles: int = 1
    free_account: bool = False
    obd_enabled: bool = False
    obd_auto_connect: bool = False

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
    mfa_setup_required: bool = False
    mfa_token: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class MfaVerifyRequest(BaseModel):
    mfa_token: str
    code: str = Field(min_length=6, max_length=10)


class MfaSetupSessionRequest(BaseModel):
    mfa_token: str


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
    max_vehicles: int | None = Field(default=None, ge=1, le=1000)
    free_account: bool | None = None
    obd_enabled: bool | None = None
    obd_auto_connect: bool | None = None


class UserAdminOut(BaseModel):
    id: str
    email: EmailStr
    display_name: str
    role: str
    is_active: bool
    mfa_enabled: bool
    max_vehicles: int = 1
    free_account: bool = False
    obd_enabled: bool = False
    obd_auto_connect: bool = False
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class UserWithVehicleCount(UserOut):
    vehicle_count: int = 0
    vehicles_remaining: int = 0
    plan: str = "free"  # free / enthusiast / garage (billing tier)
    subscription_status: str | None = None
