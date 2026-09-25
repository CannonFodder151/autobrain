"""Bookings (service scheduling) module contract.

This module defines the public interface for service scheduling and bookings.
Actual implementations live in:
- app.services.service_records (service CRUD, timeline sync)
- app.models.service (ServiceRecord, ServiceItem models)
- app.schemas.service (Service schemas)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.service import ServiceRecord, ServiceItem
    from app.schemas.service import (
        ServiceCreate, ServiceUpdate, ServiceOut,
        ServicePredictionRequest, ServicePredictionResponse,
    )

__all__ = [
    "service_or_404",
    "list_completed_services",
    "queue_due_notification",
    "finalize_service_side_effects",
    "ensure_completed_event",
    "reconcile_part_stock",
    "ServiceRecord",
    "ServiceItem",
    "ServiceCreate",
    "ServiceUpdate",
    "ServiceOut",
    "ServicePredictionRequest",
    "ServicePredictionResponse",
]


def __getattr__(name: str):
    if name in {
        "service_or_404", "list_completed_services", "queue_due_notification",
        "finalize_service_side_effects", "ensure_completed_event", "reconcile_part_stock",
    }:
        from app.services.service_records import (
            service_or_404, list_completed_services, queue_due_notification,
            finalize_service_side_effects, ensure_completed_event, reconcile_part_stock,
        )
        globals().update({
            "service_or_404": service_or_404,
            "list_completed_services": list_completed_services,
            "queue_due_notification": queue_due_notification,
            "finalize_service_side_effects": finalize_service_side_effects,
            "ensure_completed_event": ensure_completed_event,
            "reconcile_part_stock": reconcile_part_stock,
        })
        return globals()[name]
    if name in {"ServiceRecord", "ServiceItem"}:
        from app.models.service import ServiceRecord, ServiceItem
        globals()["ServiceRecord"] = ServiceRecord
        globals()["ServiceItem"] = ServiceItem
        return globals()[name]
    if name in {"ServiceCreate", "ServiceUpdate", "ServiceOut", "ServicePredictionRequest", "ServicePredictionResponse"}:
        from app.schemas.service import (
            ServiceCreate, ServiceUpdate, ServiceOut,
            ServicePredictionRequest, ServicePredictionResponse,
        )
        globals().update({
            "ServiceCreate": ServiceCreate,
            "ServiceUpdate": ServiceUpdate,
            "ServiceOut": ServiceOut,
            "ServicePredictionRequest": ServicePredictionRequest,
            "ServicePredictionResponse": ServicePredictionResponse,
        })
        return globals()[name]
    raise AttributeError(f"module 'app.modules.bookings' has no attribute '{name}'")