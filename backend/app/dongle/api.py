"""API surface: internal proxy (backend), device-edge (dongle), web GUI (ops)."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from .config import settings
from .db import get_db
from .models import FirmwareManifest, SerialWhitelist
from .schemas import ManifestCreate, ManifestOut
from .security import check_internal_key, web_basic_user, verify_device_with_backend
from .storage import Storage, get_storage
from .util import is_valid_sha256, utcnow

templates = Jinja2Templates(directory="app/dongle/templates")

internal = APIRouter(dependencies=[Depends(check_internal_key)])
device = APIRouter()
web = APIRouter()

async def _manifest_to_out(row: FirmwareManifest, storage: Storage, ttl: timedelta | None = None) -> ManifestOut:
    url = await storage.presigned_url(
        row.blob_key, ttl or timedelta(seconds=settings.SIGNED_URL_TTL_SECONDS)
    )
    return ManifestOut(
        model=row.model,
        version=row.version,
        sha256=row.sha256,
        size_bytes=row.size_bytes,
        release_notes=row.release_notes,
        created_at=row.created_at,
        blob_url=url,
    )

async def _create_manifest(payload: ManifestCreate, db: AsyncSession, storage: Storage) -> ManifestOut:
    row = FirmwareManifest(
        model=payload.model,
        version=payload.version,
        sha256=payload.sha256_canonical,
        size_bytes=payload.size_bytes,
        blob_key=payload.blob_key,
        release_notes=payload.release_notes,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            409, f"Manifest {payload.version} for {payload.model} already exists"
        )
    await db.refresh(row)
    return await _manifest_to_out(row, storage)

@internal.get("/manifests/latest")
async def internal_latest(
    model: str = Query(min_length=1, max_length=64),
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> ManifestOut:
    row = await db.scalar(
        select(FirmwareManifest)
        .where(FirmwareManifest.model == model)
        .order_by(FirmwareManifest.created_at.desc())
        .limit(1)
    )
    if row is None:
        raise HTTPException(404, "No firmware for model")
    return await _manifest_to_out(row, storage)

@internal.post("/manifests", status_code=status.HTTP_201_CREATED)
async def internal_create(
    payload: ManifestCreate,
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> ManifestOut:
    return await _create_manifest(payload, db, storage)

@internal.post("/whitelist")
async def internal_whitelist(
    serial: str = Form(..., max_length=64),
    device_id: str = Form(..., max_length=36),
    user_id: str = Form(..., max_length=36),
    paid: bool = Form(...),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    existing = await db.get(SerialWhitelist, serial)
    if paid:
        if existing is None:
            existing = SerialWhitelist(
                serial_number=serial, device_id=device_id, user_id=user_id,
                paid_at=utcnow(),
            )
            db.add(existing)
        else:
            existing.paid_at = utcnow()
            existing.device_id = device_id
            existing.user_id = user_id
    elif existing is not None:
        await db.delete(existing)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            409, f"Serial {serial} already registered to another device"
        )
    return JSONResponse(
        status_code=200,
        content={"ok": True, "serial": serial, "whitelisted": paid},
    )

@device.get("/firmware/latest")
async def device_latest(
    serial: str = Query(min_length=1, max_length=64),
    api_key: str = Query(min_length=1),
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage),
) -> ManifestOut:
    """Device-edge fetch: serial whitelist + backend paid/account gate."""
    if await db.get(SerialWhitelist, serial) is None:
        raise HTTPException(403, "Serial not whitelisted")
    info = await verify_device_with_backend(serial, api_key)
    row = await db.scalar(
        select(FirmwareManifest)
        .where(FirmwareManifest.model == info["model"])
        .order_by(FirmwareManifest.created_at.desc())
        .limit(1)
    )
    if row is None:
        raise HTTPException(404, "No firmware for model")
    return await _manifest_to_out(row, storage)

@web.get("/admin", response_class=HTMLResponse, dependencies=[Depends(web_basic_user)])
async def web_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(FirmwareManifest).order_by(FirmwareManifest.created_at.desc())
        )
    ).scalars().all()
    manifests = [
        {"id": r.id, "model": r.model, "version": r.version,
         "sha256": r.sha256, "size_bytes": r.size_bytes,
         "release_notes": r.release_notes, "created_at": r.created_at,
         "blob_key": _safe_blob_key(r.blob_key)}
        for r in rows
    ]
    serials = (
        await db.execute(select(SerialWhitelist).order_by(SerialWhitelist.added_at.desc()))
    ).scalars().all()
    return templates.TemplateResponse(request, "manifests.html", {
        "manifests": manifests,
        "serials": serials,
        "bucket": settings.MINIO_BUCKET,
    })

@web.get("/admin/login", response_class=HTMLResponse)
async def web_login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {"request": request})

@web.get("/admin/manifest/new", response_class=HTMLResponse,
         dependencies=[Depends(web_basic_user)])
async def web_new_form(request: Request):
    return templates.TemplateResponse(request, "manifest_form.html", {"action": "/admin/manifest"})

@web.post("/admin/manifest", response_model=ManifestOut,
          dependencies=[Depends(web_basic_user)])
async def web_create_manifest(
    model: str = Form(..., max_length=64),
    version: str = Form(..., max_length=32),
    sha256: str = Form(...),
    size_bytes: int = Form(..., gt=0, le=16 * 1024 * 1024),
    blob_key: str = Form(..., max_length=256),
    release_notes: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    storage: Storage = Depends(get_storage),
):
    if not is_valid_sha256(sha256):
        raise HTTPException(400, "sha256 must be 64 hex characters")
    payload = ManifestCreate(
        model=model, version=version, sha256=sha256,
        size_bytes=size_bytes, blob_key=blob_key, release_notes=release_notes,
    )
    return await _create_manifest(payload, db, storage)

def _safe_blob_key(key: str) -> str:
    return f"{key[:3]}...{key[-16:]}" if len(key) > 24 else key