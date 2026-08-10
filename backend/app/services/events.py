"""Vehicle timeline event materialisation (called by other routers after writes)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vehicle import VehicleEvent


async def add_event(
    db: AsyncSession,
    vehicle_id: str,
    event_type: str,
    title: str,
    occurred_on,
    odometer_km: int | None,
    amount: float | None,
    source_id: str,
) -> None:
    db.add(
        VehicleEvent(
            vehicle_id=vehicle_id,
            event_type=event_type,
            title=title,
            occurred_on=occurred_on,
            odometer_km=odometer_km,
            amount=amount,
            source_id=source_id,
        )
    )
