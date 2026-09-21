"""Workshop API routes for AutoBrain Shop."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token, hash_password
from app.db.session import get_db
from app.models.workshop import Workshop, WorkshopUser, WorkshopRole
from app.schemas.auth import (
    WorkshopCreate,
    WorkshopOut,
    WorkshopPage,
    WorkshopUpdate,
    WorkshopUserCreate,
    WorkshopUserOut,
)

router = APIRouter(prefix="/workshops", tags=["workshops"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


class WorkshopUserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    role: str | None = Field(default=None, pattern="^(owner|manager|tech|admin)$")
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


async def _get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkshopUser:
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = await db.get(WorkshopUser, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if payload.get("ver", 0) != user.token_version:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return user


async def _get_workshop(
    user: Annotated[WorkshopUser, Depends(_get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Workshop:
    workshop = await db.get(Workshop, user.workshop_id)
    if not workshop or not workshop.is_active:
        raise HTTPException(status_code=403, detail="Workshop not found or inactive")
    return workshop


def _require_role(*roles: WorkshopRole):
    """Dependency factory: rejects if the current user's role isn't in `roles`."""

    async def _check(
        workshop: Annotated[Workshop, Depends(_get_workshop)],
        user: Annotated[WorkshopUser, Depends(_get_current_user)],
    ) -> Workshop:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return workshop

    return _check


@router.post("", response_model=WorkshopOut, status_code=status.HTTP_201_CREATED)
async def create_workshop(
    data: WorkshopCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkshopOut:
    existing = await db.execute(select(Workshop).where(Workshop.slug == data.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Slug already taken")

    workshop = Workshop(
        name=data.name,
        slug=data.slug,
        email=data.email,
        phone=data.phone,
        address=data.address,
        city=data.city,
        state=data.state,
        postcode=data.postcode,
        country=data.country,
        abn=data.abn,
        subscription_tier=data.subscription_tier,
    )
    db.add(workshop)
    await db.flush()

    owner = WorkshopUser(
        workshop_id=workshop.id,
        email=data.email,
        display_name=data.name + " Owner",
        hashed_password=hash_password("CHANGEME-123"),
        role=WorkshopRole.OWNER,
    )
    db.add(owner)
    await db.commit()
    await db.refresh(workshop)
    return WorkshopOut.model_validate(workshop)


@router.get("", response_model=WorkshopPage)
async def list_workshops(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> WorkshopPage:
    total = (await db.execute(select(func.count(Workshop.id)))).scalar()
    result = await db.execute(
        select(Workshop)
        .order_by(Workshop.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    workshops = result.scalars().all()
    return WorkshopPage(
        items=[WorkshopOut.model_validate(w) for w in workshops],
        total=total,
        page=page,
        pages=(total + page_size - 1) // page_size,
    )


@router.get("/{workshop_id}", response_model=WorkshopOut)
async def get_workshop(
    workshop_id: str,
    workshop: Annotated[Workshop, Depends(_get_workshop)],
) -> WorkshopOut:
    return WorkshopOut.model_validate(workshop)


@router.patch("/{workshop_id}", response_model=WorkshopOut)
async def update_workshop(
    workshop_id: str,
    data: WorkshopUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    workshop: Annotated[Workshop, Depends(_require_role(WorkshopRole.OWNER, WorkshopRole.ADMIN))],
) -> WorkshopOut:
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(workshop, field, value)
    await db.commit()
    await db.refresh(workshop)
    return WorkshopOut.model_validate(workshop)


@router.delete("/{workshop_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workshop(
    workshop_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    workshop: Annotated[Workshop, Depends(_require_role(WorkshopRole.OWNER))],
) -> None:
    await db.delete(workshop)
    await db.commit()


@router.post("/{workshop_id}/users", response_model=WorkshopUserOut, status_code=status.HTTP_201_CREATED)
async def create_workshop_user(
    workshop_id: str,
    data: WorkshopUserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    workshop: Annotated[Workshop, Depends(_require_role(WorkshopRole.OWNER, WorkshopRole.ADMIN))],
) -> WorkshopUserOut:
    user_count = (await db.execute(
        select(func.count(WorkshopUser.id)).where(WorkshopUser.workshop_id == workshop_id)
    )).scalar()
    if user_count >= workshop.max_users:
        raise HTTPException(status_code=403, detail="Workshop user limit reached")

    existing = await db.execute(
        select(WorkshopUser).where(
            WorkshopUser.workshop_id == workshop_id,
            WorkshopUser.email == data.email,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already exists in this workshop")

    user = WorkshopUser(
        workshop_id=workshop_id,
        email=data.email,
        display_name=data.display_name,
        hashed_password=hash_password(data.password),
        role=WorkshopRole(data.role),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return WorkshopUserOut.model_validate(user)


@router.get("/{workshop_id}/users", response_model=list[WorkshopUserOut])
async def list_workshop_users(
    workshop_id: str,
    workshop: Annotated[Workshop, Depends(_get_workshop)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[WorkshopUserOut]:
    result = await db.execute(
        select(WorkshopUser)
        .where(WorkshopUser.workshop_id == workshop_id)
        .order_by(WorkshopUser.created_at.desc())
    )
    users = result.scalars().all()
    return [WorkshopUserOut.model_validate(u) for u in users]


@router.patch("/{workshop_id}/users/{user_id}", response_model=WorkshopUserOut)
async def update_workshop_user(
    workshop_id: str,
    user_id: str,
    data: WorkshopUserUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    workshop: Annotated[Workshop, Depends(_require_role(WorkshopRole.OWNER, WorkshopRole.ADMIN))],
) -> WorkshopUserOut:
    user = await db.get(WorkshopUser, user_id)
    if not user or user.workshop_id != workshop_id:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "password" and value:
            value = hash_password(value)
        setattr(user, field, value)
    await db.commit()
    await db.refresh(user)
    return WorkshopUserOut.model_validate(user)


@router.delete("/{workshop_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workshop_user(
    workshop_id: str,
    user_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    workshop: Annotated[Workshop, Depends(_require_role(WorkshopRole.OWNER, WorkshopRole.ADMIN))],
) -> None:
    user = await db.get(WorkshopUser, user_id)
    if not user or user.workshop_id != workshop_id:
        raise HTTPException(status_code=404, detail="User not found")

    if user.role == WorkshopRole.OWNER:
        raise HTTPException(status_code=403, detail="Cannot delete workshop owner")

    await db.delete(user)
    await db.commit()


