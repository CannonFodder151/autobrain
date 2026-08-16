"""ORM models. Imported for Alembic autogenerate and app wiring."""

from app.models.user import User
from app.models.vehicle import Vehicle, VehicleEvent
from app.models.logbook import LogEntry
from app.models.obd import ObdCode
from app.models.service import ServiceRecord, ServiceItem
from app.models.fuel import FuelLog
from app.models.diagnostic import Diagnostic
from app.models.mod import Modification
from app.models.part import Part, PartMovement
from app.models.receipt import Receipt, ExtractedItem
from app.models.valuation import ValuationSnapshot
from app.models.market_listing import MarketListingCache
from app.models.notification import NotificationPreference, NotificationDelivery
from app.models.share import VehicleShare
from app.models.refresh_token import RevokedRefreshToken
from app.social.models import (
    SocialBuild,
    SocialComment,
    SocialLike,
    SocialPhoto,
    SocialRemoteTombstone,
    SocialServerConfig,
    SocialShareScope,
)

__all__ = [
    "User",
    "Vehicle",
    "VehicleEvent",
    "LogEntry",
    "ObdCode",
    "ServiceRecord",
    "ServiceItem",
    "FuelLog",
    "Diagnostic",
    "Modification",
    "Part",
    "PartMovement",
    "Receipt",
    "ExtractedItem",
    "ValuationSnapshot",
    "MarketListingCache",
    "NotificationPreference",
    "NotificationDelivery",
    "VehicleShare",
    "RevokedRefreshToken",
    "SocialBuild",
    "SocialPhoto",
    "SocialComment",
    "SocialLike",
    "SocialShareScope",
    "SocialServerConfig",
    "SocialRemoteTombstone",
]
