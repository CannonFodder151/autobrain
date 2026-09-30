"""Community Garage admin toggles (AUT-332): server config + federation
registration. Separate from moderation (see ``moderation.py``)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.config import settings
from app.db.session import get_db

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class _SocialConfigUpdate(BaseModel):
    feature_enabled: bool | None = None
    federation_enabled: bool | None = None
    server_name: str | None = None
    server_email: str | None = None


@router.get("/social")
async def social_config(db: AsyncSession = Depends(get_db)) -> dict:
    from app.social.models import get_server_config

    cfg = await get_server_config(db)
    return {
        "feature_enabled": cfg.feature_enabled,
        "federation_enabled": cfg.federation_enabled,
        "server_name": cfg.server_name,
        "server_email": cfg.server_email,
        "hub_status": cfg.hub_status,
        "hub_server_id": cfg.hub_server_id,
        "hub_url": cfg.server_hub_url or settings.SOCIAL_FEDERATION_HUB_URL,
    }


@router.patch("/social")
async def update_social_config(
    payload: _SocialConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.social.models import get_server_config

    cfg = await get_server_config(db)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(cfg, key, value)
    await db.commit()
    await db.refresh(cfg)
    return {"message": "Community Garage settings updated", "feature_enabled": cfg.feature_enabled}


@router.post("/social/register")
async def register_social_server(db: AsyncSession = Depends(get_db)) -> dict:
    """Register this server with the federation hub (req 14)."""
    from app.social import federation as fed
    from app.social.models import get_server_config

    cfg = await get_server_config(db)
    if not cfg.server_name or not cfg.server_email:
        raise HTTPException(
            status_code=400,
            detail="Set server_name and server_email first (PATCH /admin/social)",
        )
    # AUT-758: the server keypair is generated once and reused on every
    # (re)registration attempt — it must not rotate while trying to join.
    if cfg.hub_private_key:
        private_key = cfg.hub_private_key
        public_key = fed.public_key_from_private(private_key)
    else:
        private_key, public_key = fed.generate_keypair()
        cfg.hub_private_key = private_key
    try:
        result = await fed.register(cfg, cfg.server_name, cfg.server_email, public_key)
    except fed.FederationUnavailable as exc:
        cfg.hub_status = "error"
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Hub unreachable: {exc}")
    cfg.hub_status = "registered" if result.get("status") in ("approved", "registered") else "pending"
    cfg.hub_server_id = str(result.get("server_id"))
    cfg.hub_api_key = str(result.get("api_key"))
    cfg.hub_private_key = private_key
    await db.commit()
    return {
        "hub_status": cfg.hub_status,
        "hub_server_id": cfg.hub_server_id,
        "server_name": cfg.server_name,
        "license_status": result.get("license_status"),
    }


@router.post("/social/unregister")
async def unregister_social_server(db: AsyncSession = Depends(get_db)) -> dict:
    from app.social.models import get_server_config

    cfg = await get_server_config(db)
    cfg.hub_status = "unregistered"
    cfg.hub_server_id = None
    cfg.hub_api_key = None
    cfg.hub_private_key = None
    await db.commit()
    return {"message": "Server removed from the federation hub", "hub_status": cfg.hub_status}
