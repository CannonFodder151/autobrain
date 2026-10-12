"""Small pure helpers shared across the service."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

_SHA256_RE = re.compile(r"(?i)^[0-9a-f]{64}$")

def utcnow() -> datetime:
    """Naive UTC (SQLite-friendly; tz-aware values don't round-trip on SQLite)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

def is_valid_sha256(value: str) -> bool:
    return bool(_SHA256_RE.match(value))

def sha256_hex(data: bytes) -> str:
    return __import__("hashlib").sha256(data).hexdigest()