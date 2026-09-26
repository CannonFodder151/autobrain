"""Cross-domain utility helpers.

These are pure functions with no DB or I/O so they can be imported from any
module without creating a dependency cycle.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from typing import Iterable


def utc_now() -> datetime:
    """Current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


def iso_date(value: date | datetime | str | None) -> str | None:
    """Render a date/datetime/str as an ISO-8601 date string."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def sha256(value: str) -> str:
    """Return a stable hex SHA-256 of the given string."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


_slug_strip = re.compile(r"[^\w\s-]", flags=re.UNICODE)
_slug_space = re.compile(r"[\s_-]+")


def slugify(value: str) -> str:
    """Lowercase, hyphen-separated slug suitable for URLs / identifiers."""
    value = _slug_strip.sub("", value).strip().lower()
    return _slug_space.sub("-", value)


def chunked(items: Iterable, size: int) -> Iterable[list]:
    """Yield successive `size`-sized chunks of `items`."""
    if size <= 0:
        raise ValueError("chunk size must be positive")
    chunk: list = []
    for item in items:
        chunk.append(item)
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def clamp(value: float, low: float, high: float) -> float:
    """Clamp `value` to the inclusive range [low, high]."""
    return max(low, min(high, value))


__all__ = [
    "utc_now",
    "iso_date",
    "sha256",
    "slugify",
    "chunked",
    "clamp",
]