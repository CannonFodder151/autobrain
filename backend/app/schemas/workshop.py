"""Workshop schemas."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Role(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    TECH = "tech"


class WorkshopCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    address: Optional[str] = None
    phone: Optional[str] = None


class WorkshopUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    address: Optional[str] = None
    phone: Optional[str] = None


class WorkshopOut(BaseModel):
    id: str
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None


class WorkshopUserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    role: Role = Role.TECH


class WorkshopUserUpdate(BaseModel):
    role: Optional[Role] = None
    username: Optional[str] = Field(None, min_length=1, max_length=50)


class WorkshopUserOut(BaseModel):
    id: str
    workshop_id: str
    username: str
    role: Role