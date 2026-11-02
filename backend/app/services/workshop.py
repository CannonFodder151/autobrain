"""Workshop service: in-memory store + RBAC."""

from __future__ import annotations

import uuid
from typing import Dict, List, Optional

from app.schemas.workshop import Role, WorkshopCreate, WorkshopUpdate, WorkshopUserCreate, WorkshopUserUpdate

_ADMIN_ROLES = {Role.OWNER, Role.ADMIN}
_MANAGER_ROLES = {Role.OWNER, Role.ADMIN, Role.MANAGER}

_workshops: Dict[str, dict] = {}
_users: Dict[str, dict] = {}


def _can_create_user(role: Role) -> bool:
    return role in _MANAGER_ROLES


def _can_manage(role: Role) -> bool:
    return role in _ADMIN_ROLES


def create_workshop(data: WorkshopCreate) -> dict:
    wid = str(uuid.uuid4())
    w = {"id": wid, "name": data.name, "address": data.address, "phone": data.phone}
    _workshops[wid] = w
    return w


def get_workshop(wid: str) -> Optional[dict]:
    return _workshops.get(wid)


def list_workshops() -> List[dict]:
    return list(_workshops.values())


def update_workshop(wid: str, data: WorkshopUpdate) -> Optional[dict]:
    w = _workshops.get(wid)
    if not w:
        return None
    if data.name is not None:
        w["name"] = data.name
    if data.address is not None:
        w["address"] = data.address
    if data.phone is not None:
        w["phone"] = data.phone
    return w


def delete_workshop(wid: str) -> bool:
    if wid not in _workshops:
        return False
    del _workshops[wid]
    for uid in [u for u, udata in _users.items() if udata["workshop_id"] == wid]:
        del _users[uid]
    return True


def create_user(wid: str, data: WorkshopUserCreate, requester_role: Role) -> Optional[dict]:
    if not _can_create_user(requester_role):
        return None
    if wid not in _workshops:
        return None
    uid = str(uuid.uuid4())
    u = {"id": uid, "workshop_id": wid, "username": data.username, "role": data.role}
    _users[uid] = u
    return u


def get_user(uid: str) -> Optional[dict]:
    return _users.get(uid)


def list_users(wid: str) -> List[dict]:
    return [u for u in _users.values() if u["workshop_id"] == wid]


def update_user(uid: str, data: WorkshopUserUpdate, requester_role: Role) -> Optional[dict]:
    if not _can_create_user(requester_role):
        return None
    u = _users.get(uid)
    if not u:
        return None
    if data.username is not None:
        u["username"] = data.username
    if data.role is not None:
        u["role"] = data.role
    return u


def delete_user(uid: str, requester_role: Role) -> bool:
    if not _can_manage(requester_role):
        return False
    if uid not in _users:
        return False
    del _users[uid]
    return True