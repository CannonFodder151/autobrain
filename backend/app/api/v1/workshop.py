"""Workshop CRUD and user management API with RBAC."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Path

from app.schemas.workshop import (
    WorkshopCreate,
    WorkshopOut,
    WorkshopUpdate,
    WorkshopUserCreate,
    WorkshopUserOut,
    WorkshopUserUpdate,
)
from app.services.workshop import (
    create_workshop,
    get_workshop,
    list_workshops,
    update_workshop,
    delete_workshop,
    create_user,
    list_users,
    update_user,
    delete_user,
)

router = APIRouter()


def _requester_role(x_role: Optional[str]) -> str:
    return x_role or "tech"


@router.post("/workshops", response_model=WorkshopOut)
async def create_w(body: WorkshopCreate, x_role: Optional[str] = Header(None)):
    if _requester_role(x_role) not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    w = create_workshop(body)
    return WorkshopOut(**w)


@router.get("/workshops", response_model=list[WorkshopOut])
async def list_w():
    return [WorkshopOut(**w) for w in list_workshops()]


@router.get("/workshops/{workshop_id}", response_model=WorkshopOut)
async def get_w(workshop_id: str = Path(...)):
    w = get_workshop(workshop_id)
    if not w:
        raise HTTPException(status_code=404, detail="Workshop not found")
    return WorkshopOut(**w)


@router.patch("/workshops/{workshop_id}", response_model=WorkshopOut)
async def update_w(body: WorkshopUpdate, workshop_id: str = Path(...), x_role: Optional[str] = Header(None)):
    if _requester_role(x_role) not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    w = update_workshop(workshop_id, body)
    if not w:
        raise HTTPException(status_code=404, detail="Workshop not found")
    return WorkshopOut(**w)


@router.delete("/workshops/{workshop_id}")
async def delete_w(workshop_id: str = Path(...), x_role: Optional[str] = Header(None)):
    if _requester_role(x_role) not in ("owner", "admin"):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not delete_workshop(workshop_id):
        raise HTTPException(status_code=404, detail="Workshop not found")
    return {"deleted": True}


@router.post("/workshops/{workshop_id}/users", response_model=WorkshopUserOut)
async def create_u(body: WorkshopUserCreate, workshop_id: str = Path(...), x_role: Optional[str] = Header(None)):
    from app.schemas.workshop import Role

    try:
        role = Role(_requester_role(x_role))
    except ValueError:
        role = Role.TECH
    u = create_user(workshop_id, body, role)
    if not u:
        raise HTTPException(status_code=403, detail="Forbidden or workshop not found")
    return WorkshopUserOut(**u)


@router.get("/workshops/{workshop_id}/users", response_model=list[WorkshopUserOut])
async def list_u(workshop_id: str = Path(...)):
    return [WorkshopUserOut(**u) for u in list_users(workshop_id)]


@router.patch("/workshops/{workshop_id}/users/{user_id}", response_model=WorkshopUserOut)
async def update_u(body: WorkshopUserUpdate, workshop_id: str = Path(...), user_id: str = Path(...), x_role: Optional[str] = Header(None)):
    from app.schemas.workshop import Role

    try:
        role = Role(_requester_role(x_role))
    except ValueError:
        role = Role.TECH
    u = update_user(user_id, body, role)
    if not u:
        raise HTTPException(status_code=403, detail="Forbidden or user not found")
    return WorkshopUserOut(**u)


@router.delete("/workshops/{workshop_id}/users/{user_id}")
async def delete_u(workshop_id: str = Path(...), user_id: str = Path(...), x_role: Optional[str] = Header(None)):
    from app.schemas.workshop import Role

    try:
        role = Role(_requester_role(x_role))
    except ValueError:
        role = Role.TECH
    if not delete_user(user_id, role):
        raise HTTPException(status_code=403, detail="Forbidden or user not found")
    return {"deleted": True}