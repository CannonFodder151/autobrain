"""Auth helpers: internal API key, web-GUI basic auth, device-edge verification
delegated to the AutoBrain backend."""

from __future__ import annotations

import hmac

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import settings

basic = HTTPBasic(auto_error=False)

def check_internal_key(request: Request) -> None:
    expected = settings.api_key()
    supplied = request.headers.get("X-Internal-Api-Key", "")
    if not expected or not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Invalid internal API key")

def web_basic_user(
    credentials: HTTPBasicCredentials | None = Depends(basic),
) -> str:
    expected_user = settings.WEB_UI_BASIC_USER
    expected_pass = settings.web_password()
    if (
        not credentials
        or not expected_pass
        or credentials.username != expected_user
        or not hmac.compare_digest(credentials.password, expected_pass)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Basic"},
            detail="Authentication required",
        )
    return credentials.username

async def verify_device_with_backend(serial: str, api_key: str) -> dict:
    """Ask the AutoBrain backend whether [api_key] belongs to a device whose
    reported serial is [serial], and whether that account is paid.

    Returns {device_id, user_id, paid}. Fails closed: any backend error denies.
    """
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing device API key")
    payload = {"serial": serial, "api_key": api_key}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{settings.AUTOBRAIN_BACKEND_URL.rstrip('/')}/api/v1/devices/verify",
                json=payload,
                headers={"X-Internal-Api-Key": settings.api_key()},
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Backend unavailable")
    if resp.status_code == 404:
        raise HTTPException(status_code=403, detail="Serial or device not registered")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="Backend verification failed")
    try:
        data = resp.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="Backend returned invalid JSON")
    if data.get("serial_matched") is not True:
        raise HTTPException(status_code=403, detail="Serial does not match device")
    if not data.get("paid"):
        raise HTTPException(status_code=402, detail="Paid account required")
    model = data.get("model")
    if not model:
        raise HTTPException(status_code=404, detail="No firmware model reported for device")
    return {"device_id": data["device_id"], "user_id": data["user_id"], "model": model}