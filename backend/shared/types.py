"""Common shared types."""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class Pagination(BaseModel):
    skip: int = 0
    limit: int = 50
