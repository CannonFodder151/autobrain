"""Notification preference routes (per vehicle)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_write
from app.services.ownership import get_accessible_vehicle
from app.db.session import get_db
from app.models.notification import NotificationPreference
from app.models.user import User
from app.schemas.notification import NotificationPreferenceIn, NotificationPreferenceOut

router = APIRouter(prefix="/vehicles/{vehicle_id}/notifications", tags=["notifications"])


@router.get("", response_model=NotificationPreferenceOut)
async def get_preference(
    vehicle_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> NotificationPreference:
    await get_accessible_vehicle(db, vehicle_id, user)
    pref = await db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user.id,
            NotificationPreference.vehicle_id == vehicle_id,
        )
    )
    if not pref:
        # Return defaults without persisting (demo accounts are read-only).
        pref = NotificationPreference(user_id=user.id, vehicle_id=vehicle_id)
    return pref


@router.put("", response_model=NotificationPreferenceOut)
async def update_preference(
    vehicle_id: str,
    payload: NotificationPreferenceIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> NotificationPreference:
    await get_accessible_vehicle(db, vehicle_id, user)
    pref = await db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user.id,
            NotificationPreference.vehicle_id == vehicle_id,
        )
    )
    if not pref:
        pref = NotificationPreference(user_id=user.id, vehicle_id=vehicle_id)
        db.add(pref)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(pref, key, value)
    await db.commit()
    await db.refresh(pref)
    return pref
