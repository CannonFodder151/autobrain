"""Shared package for cross-domain backend modules.

Provides types, utilities, and config re-exports used by all domain modules.
"""

from app.shared.types import (
    UserId,
    VehicleId,
    ModificationId,
    BookingId,
    new_id,
    JSON,
)
from app.shared.utils import (
    utc_now,
    iso_date,
    sha256,
    slugify,
    chunked,
    clamp,
)
from app.shared.config import settings

__all__ = [
    "UserId",
    "VehicleId",
    "ModificationId",
    "BookingId",
    "new_id",
    "JSON",
    "utc_now",
    "iso_date",
    "sha256",
    "slugify",
    "chunked",
    "clamp",
    "settings",
]