"""Vehicle share invite endpoints: accept/deny invitations, remove access."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.share import VehicleShare
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.vehicle import ShareInviteOut

router = APIRouter(prefix="/vehicle-shares", tags=["shares"])


async def _get_share(db: AsyncSession, share_id: str, user: User) -> VehicleShare:
    """Fetch a share the user is party to (invitee or vehicle owner)."""
    share = await db.get(VehicleShare, share_id)
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found")
    vehicle = await db.get(Vehicle, share.vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Share not found")
    if user.id != share.invitee_user_id and user.id != vehicle.user_id:
        raise HTTPException(status_code=404, detail="Share not found")
    return share


async def _invite_out(db: AsyncSession, share: VehicleShare) -> dict:
    vehicle = await db.get(Vehicle, share.vehicle_id)
    owner = await db.get(User, vehicle.user_id)
    return {
        "id": share.id,
        "status": share.status,
        "vehicle_id": vehicle.id,
        "vehicle_nickname": vehicle.nickname,
        "owner_name": owner.display_name,
        "created_at": share.created_at,
    }


@router.get("", response_model=list[ShareInviteOut])
async def list_invites(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """Shares (pending + accepted) where the current user is the invitee."""
    rows = (await db.execute(
        select(VehicleShare, Vehicle, User)
        .join(Vehicle, Vehicle.id == VehicleShare.vehicle_id)
        .join(User, User.id == Vehicle.user_id)
        .where(VehicleShare.invitee_user_id == user.id)
        .order_by(VehicleShare.created_at.desc())
    )).all()
    return [
        {
            "id": s.id,
            "status": s.status,
            "vehicle_id": v.id,
            "vehicle_nickname": v.nickname,
            "owner_name": owner.display_name,
            "created_at": s.created_at,
        }
        for s, v, owner in rows
    ]


@router.post("/{share_id}/accept", response_model=ShareInviteOut)
async def accept_share(
    share_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Accept a pending share invitation (invitee only)."""
    share = await _get_share(db, share_id, user)
    if user.id != share.invitee_user_id:
        raise HTTPException(status_code=404, detail="Share not found")
    if share.status == "accepted":
        raise HTTPException(status_code=409, detail="Share already accepted")
    share.status = "accepted"
    await db.commit()
    return await _invite_out(db, share)


@router.post("/{share_id}/deny", status_code=204)
async def deny_share(
    share_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Decline a pending share invitation (invitee only); removes the share."""
    share = await _get_share(db, share_id, user)
    if user.id != share.invitee_user_id:
        raise HTTPException(status_code=404, detail="Share not found")
    if share.status == "accepted":
        raise HTTPException(status_code=409, detail="Share already accepted")
    await db.delete(share)
    await db.commit()


@router.delete("/{share_id}", status_code=204)
async def remove_share(
    share_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Revoke access: the vehicle owner removes a shareee, or an invitee
    removes a vehicle shared with them."""
    share = await _get_share(db, share_id, user)
    await db.delete(share)
    await db.commit()
