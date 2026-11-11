"""Pydantic schemas for the public developer API (AUT-423)."""

from typing import Optional

from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    label: str = Field(..., max_length=120)
    scopes: Optional[list[str]] = None
    rate_limit: Optional[int] = Field(None, description="Requests per window")
    rate_window_seconds: Optional[int] = Field(None, description="Window in seconds")


class ApiKeyUpdate(BaseModel):
    label: Optional[str] = Field(None, max_length=120)
    scopes: Optional[list[str]] = None
    rate_limit: Optional[int] = None
    rate_window_seconds: Optional[int] = None


class ApiKeyOut(BaseModel):
    id: str
    label: str
    prefix: str
    scopes: list[str]
    rate_limit: Optional[int] = None
    rate_window_seconds: Optional[int] = None
    last_used_at: Optional[str] = None
    created_at: Optional[str] = None
    revoked_at: Optional[str] = None
    is_active: bool = True
    key: Optional[str] = None  # Only present on create response


class WebhookCreate(BaseModel):
    label: str = Field(..., max_length=120)
    url: str = Field(..., max_length=512)
    events: list[str]
    max_retries: Optional[int] = Field(5, ge=1, le=20)


class WebhookUpdate(BaseModel):
    label: Optional[str] = Field(None, max_length=120)
    url: Optional[str] = Field(None, max_length=512)
    events: Optional[list[str]] = None
    status: Optional[str] = None
    max_retries: Optional[int] = Field(None, ge=1, le=20)


class WebhookOut(BaseModel):
    id: str
    label: str
    url: str
    events: list[str]
    secret_prefix: str
    status: str
    max_retries: int
    consecutive_failures: int
    last_delivered_at: Optional[str] = None
    last_failed_at: Optional[str] = None
    last_failure_reason: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    secret: Optional[str] = None  # Only on create/update


class WebhookTestRequest(BaseModel):
    message: Optional[str] = None


class WebhookDeliveryOut(BaseModel):
    id: str
    webhook_id: str
    event_type: str
    payload: Optional[dict] = None
    http_status: Optional[int] = None
    error: Optional[str] = None
    attempts: int
    next_retry_at: Optional[str] = None
    created_at: Optional[str] = None
    delivered_at: Optional[str] = None