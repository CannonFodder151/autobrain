"""Pydantic schemas for the firmware manifest + telemetry (mirrors backend)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

SHA256_RE = r"(?i)^[0-9a-f]{64}$"

class ManifestOut(BaseModel):
    model: str
    version: str
    sha256: str
    size_bytes: int
    release_notes: str | None
    created_at: datetime
    blob_url: str

class ManifestCreate(BaseModel):
    model: str = Field(min_length=1, max_length=64)
    version: str = Field(min_length=1, max_length=32)
    sha256: str = Field(pattern=SHA256_RE)
    size_bytes: int = Field(gt=0, le=16 * 1024 * 1024)
    blob_key: str = Field(min_length=1, max_length=256)
    release_notes: str | None = Field(default=None, max_length=4000)

    @property
    def sha256_canonical(self) -> str:
        return self.sha256.lower()