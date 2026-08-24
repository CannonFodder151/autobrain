"""Merch store routes (AUT-1540): catalogue, checkout with shipping, orders."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.billing import CheckoutResponse
from app.services import merch as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/merch", tags=["merch"])

_NOT_CONFIGURED = "Payments are not configured on this server"


class MerchCheckoutRequest(BaseModel):
    product_id: str = Field(min_length=1)
    quantity: int = Field(default=1, ge=1, le=10)


@router.get("/catalog")
async def catalog() -> dict:
    """Public merch catalogue (no auth)."""
    return svc.catalog()


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    payload: MerchCheckoutRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CheckoutResponse:
    """Stripe Checkout for a physical product; collects the shipping address."""
    try:
        url = await svc.create_checkout_session(db, user, payload.product_id, payload.quantity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        logger.exception("merch_checkout_failed")
        raise HTTPException(status_code=503, detail=_NOT_CONFIGURED)
    return CheckoutResponse(url=url)


@router.get("/orders")
async def orders(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """The signed-in user's merch order history."""
    return await svc.list_orders(db, user)
