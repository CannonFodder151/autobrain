"""VASS (Vehicle Assessment Safety System) API routes.

Deterministic compliance checks for Australian vehicle modifications.
Rules are seeded from ADR/VSI/VSB6 standards.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_write
from app.db.session import get_db
from app.models.vass import VASRule, VASCheck, ComplianceStatus
from app.models.user import User
from app.schemas.vass import (
    VASRuleCreate,
    VASRuleOut,
    VASRuleUpdate,
    VASCheckRequest,
    VASCheckResponse,
)
from app.services.vass import check_vass

router = APIRouter(prefix="/vass", tags=["vass"])


@router.post("/check", response_model=VASCheckResponse)
async def vass_check(
    payload: VASCheckRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> VASCheckResponse:
    """Check a modification against Australian vehicle standards.
    
    Deterministic rule-based check using the VASS rules table.
    Returns PASS/FAIL/CONDITIONAL with applicable standard references.
    """
    result = await check_vass(
        db,
        mod_category=payload.mod_category,
        mod_name=payload.mod_name,
        vehicle_class=payload.vehicle_class,
        mod_description=payload.mod_description,
    )
    return result


@router.get("/rules", response_model=list[VASRuleOut])
async def list_rules(
    mod_category: Optional[str] = None,
    vehicle_class: Optional[str] = None,
    is_active: bool = True,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[VASRule]:
    """List VASS rules with optional filters."""
    query = select(VASRule).where(VASRule.is_active == is_active)
    if mod_category:
        query = query.where(VASRule.mod_category == mod_category)
    if vehicle_class:
        query = query.where(VASRule.vehicle_class == vehicle_class)
    result = await db.execute(query.order_by(VASRule.standard_ref))
    return list(result.scalars().all())


@router.post("/rules", response_model=VASRuleOut, status_code=201)
async def create_rule(
    payload: VASRuleCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_write),
) -> VASRule:
    """Create a new VASS rule (admin use)."""
    # Check for duplicate
    existing = await db.execute(
        select(VASRule).where(
            and_(
                VASRule.standard_ref == payload.standard_ref,
                VASRule.vehicle_class == payload.vehicle_class,
                VASRule.mod_category == payload.mod_category,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Rule already exists for this standard reference, vehicle class, and modification category",
        )
    
    rule = VASRule(**payload.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.patch("/rules/{rule_id}", response_model=VASRuleOut)
async def update_rule(
    rule_id: str,
    payload: VASRuleUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_write),
) -> VASRule:
    """Update a VASS rule (admin use)."""
    rule = await db.get(VASRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="VASS rule not found")
    
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, key, value)
    
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_write),
) -> None:
    """Delete a VASS rule (admin use)."""
    rule = await db.get(VASRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="VASS rule not found")
    
    await db.delete(rule)
    await db.commit()