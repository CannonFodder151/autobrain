"""Admin subpackage Pydantic request models."""

from pydantic import BaseModel


class _SocialConfigUpdate(BaseModel):
    feature_enabled: bool | None = None
    federation_enabled: bool | None = None
    server_name: str | None = None
    server_email: str | None = None


class _IssueModerationUpdate(BaseModel):
    status_hidden: bool | None = None
    status: str | None = None