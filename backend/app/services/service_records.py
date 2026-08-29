"""Service-record business logic: timeline sync, part-stock reconciliation.

Extracted from api/v1/services.py so the router stays thin and the rules are
unit-testable (AUT-126 #12).
"""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.services.events import add_event
from app.models.diagnostic import Diagnostic
from app.models.part import Part, PartMovement
from app.models.service import ServiceRecord
from app.models.vehicle import VehicleEvent


def load_options() -> selectinload:
    """Eager-load service items (shared by list + detail queries)."""
    return selectinload(ServiceRecord.items)


async def service_or_404(db: AsyncSession, vehicle_id: str, service_id: str) -> ServiceRecord:
    record = await db.scalar(
        select(ServiceRecord)
        .options(load_options())
        .where(ServiceRecord.id == service_id, ServiceRecord.vehicle_id == vehicle_id)
    )
    if not record:
        raise HTTPException(status_code=404, detail="Service not found")
    return record


async def ensure_completed_event(db: AsyncSession, record: ServiceRecord) -> None:
    """Sync the timeline event with the service record.

    Completed services appear on the timeline; future/scheduled ones drop off
    until they are completed again (AUT-18).
    """
    existing = await db.scalar(
        select(VehicleEvent).where(VehicleEvent.source_id == record.id)
    )
    if record.status != "completed":
        if existing:
            await db.delete(existing)
        return
    if existing:
        existing.title = f"{record.service_type.title()} service @ {record.odometer_km:,} km"
        existing.occurred_on = record.completed_date or record.service_date
        existing.odometer_km = record.odometer_km
        existing.amount = record.cost
        return
    await add_event(
        db, record.vehicle_id, "service",
        f"{record.service_type.title()} service @ {record.odometer_km:,} km",
        record.completed_date or record.service_date,
        record.odometer_km, record.cost, record.id,
    )


async def resolve_linked_diagnostics(db: AsyncSession, record: ServiceRecord) -> None:
    """Green-tick diagnostics whose scheduled repair service is now completed."""
    if record.status != "completed":
        return
    diags = list((await db.scalars(
        select(Diagnostic).where(Diagnostic.linked_service_id == record.id, Diagnostic.status != "resolved")
    )).all())
    for diag in diags:
        diag.status = "resolved"
        diag.resolved_at = datetime.now(timezone.utc)


async def reconcile_part_stock(
    db: AsyncSession, vehicle_id: str, service_id: str, items, deduct: bool
) -> None:
    """Keep parts inventory in sync with a completed service.

    Reverses any prior stock movements recorded against this service (so the
    operation is idempotent across edits), then — when the service is
    completed — deducts the used quantities and logs a PartMovement per part.
    """
    prev = list((await db.scalars(
        select(PartMovement).where(PartMovement.service_id == service_id)
    )).all())
    for mv in prev:
        part = await db.get(Part, mv.part_id)
        if part:
            part.quantity -= mv.delta  # undo: delta is negative for a deduction
    if prev:
        await db.execute(
            PartMovement.__table__.delete().where(PartMovement.service_id == service_id)
        )

    if not deduct:
        return

    used: dict[str, int] = {}
    for it in items:
        part_id = it.part_id
        if part_id:
            used[part_id] = used.get(part_id, 0) + int(it.quantity or 1)
    for part_id, qty in used.items():
        part = await db.get(Part, part_id)
        if not part or part.vehicle_id != vehicle_id:
            raise HTTPException(status_code=400, detail="Part not found")
        if part.quantity < qty:
            raise HTTPException(status_code=400, detail=f"Insufficient stock for {part.name}")
        part.quantity -= qty
        db.add(
            PartMovement(part_id=part_id, delta=-qty, reason="service", service_id=service_id)
        )


async def finalize_service_side_effects(
    db: AsyncSession, vehicle_id: str, record: ServiceRecord, items
) -> None:
    """Run the shared post-write side effects for create/update of a service:
    stock reconciliation, timeline event sync, diagnostic resolution."""
    await reconcile_part_stock(db, vehicle_id, record.id, items, record.status == "completed")
    await ensure_completed_event(db, record)
    await resolve_linked_diagnostics(db, record)


async def queue_due_notification(db: AsyncSession, vehicle_id: str, record: ServiceRecord) -> None:
    """Send the due-soon notification sweep when a service carries a due marker."""
    if record.next_due_km or record.next_due_date:
        from app.workers.tasks import fire_and_forget, check_due_notifications
        fire_and_forget(check_due_notifications, vehicle_id)


async def list_completed_services(db: AsyncSession, vehicle_id: str) -> list[ServiceRecord]:
    """Completed service history (exports / predictions) — future ones excluded."""
    rows = await db.scalars(
        select(ServiceRecord)
        .options(load_options())
        .where(
            ServiceRecord.vehicle_id == vehicle_id,
            ServiceRecord.status == "completed",
        )
        .order_by(ServiceRecord.service_date)
    )
    return list(rows)
