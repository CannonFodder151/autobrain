"""Notification engine: evaluates due services and delivers alerts.

Delivery channels (per user preference):
- Email  — always via the global system SMTP (credentials are never exposed).
- Discord — a webhook URL the user configures themselves.
- Push   — Firebase Cloud Messaging (FCM) if an FCM_SERVER_KEY is configured.

Triggers:
- Service due within N days (next_due_date) or N km (next_due_km vs odometer).
- Fuel gap: odometer travelled since last fuel fill exceeds N km.
Evaluated after service writes, after fuel writes, and by the daily Celery beat.
Deduplicated via the notification_deliveries table (per vehicle + kind).
"""

import asyncio
import html
import json
import logging
import re
from datetime import date, timedelta

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models.notification import NotificationDelivery, NotificationPreference
from app.models.service import ServiceRecord
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services import email as mail
from sqlalchemy import select

_DISCORD_WEBHOOK_RE = re.compile(
    r"^https://discord(?:app)?\.com/api/webhooks/\d+/[\w-]+$"
)

logger = get_logger(__name__)

_loop: asyncio.AbstractEventLoop | None = None


def _run(coro):
    """Run a coroutine on a single persistent loop (async engine binds to one)."""
    global _loop
    try:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_loop)
        return _loop.run_until_complete(coro)
    except Exception:
        logger.exception("notification_task_failed")
        raise


# --- Delivery helpers -------------------------------------------------------

async def _send_email(to_email: str, display_name: str, subject: str, html: str, text: str) -> bool:
    return await mail.send_email(to_email, subject, html, text)


async def _send_discord(webhook_url: str, title: str, description: str) -> bool:
    if not webhook_url:
        return False
    if not _DISCORD_WEBHOOK_RE.match(webhook_url):
        logger.warning("discord_webhook_rejected", url=webhook_url[:80])
        return False
    payload = {
        "content": None,
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": 0x00B7FF,
            }
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            resp = await client.post(webhook_url, json=payload)
        ok = resp.status_code in (200, 204)
        if not ok:
            logger.warning("discord_webhook_failed", status=resp.status_code)
        return ok
    except Exception as exc:
        logger.warning("discord_webhook_error", error=str(exc))
        return False


async def _send_push(fcm_token: str, title: str, body: str) -> bool:
    if not fcm_token or not settings.FCM_SERVER_KEY:
        return False
    payload = {
        "message": {
            "token": fcm_token,
            "notification": {"title": title, "body": body},
        }
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://fcm.googleapis.com/v1/projects/_/messages:send",
                headers={"Authorization": f"Bearer {settings.FCM_SERVER_KEY}"},
                json=payload,
            )
        ok = resp.status_code == 200
        if not ok:
            logger.warning("fcm_push_failed", status=resp.status_code)
        return ok
    except Exception as exc:
        logger.warning("fcm_push_error", error=str(exc))
        return False


def _due_badge_html(kind: str, value: float | None) -> str:
    if kind == "days" and value is not None:
        return f"{value:,.0f} day{'s' if value != 1 else ''}"
    if kind == "km" and value is not None:
        return f"{value:,.0f} km"
    return "now"


async def deliver_due_service(db, pref: NotificationPreference, vehicle: Vehicle,
                              service: ServiceRecord, kind: str, due_in: float | None,
                              channels_sent: list[str]) -> None:
    """Send a service-due alert on the channels the user enabled (once)."""
    channels = []
    title = f"{vehicle.nickname or vehicle.model or 'Vehicle'} service due"
    due_txt = _due_badge_html(kind, due_in)
    description = (
        f"Next {service.service_type} service is due in **{due_txt}**.\n"
        f"Odometer: {vehicle.odometer_km or 0:,} km"
        + (f" · Next due: {service.next_due_date.isoformat()}" if service.next_due_date else "")
    )

    if pref.email_enabled:
        user = await db.get(User, pref.user_id)
        if user:
            subject = title
            safe_name = html.escape(user.display_name)
            text = f"Hi {user.display_name},\n\n{description}"
            html = mail._branding(
                f'<p style="color:#F5F7FA">Hi <b>{safe_name}</b>,</p>'
                f'<p style="color:#E5ECF5">{description.replace("**", "")}</p>'
            )
            if await _send_email(user.email, user.display_name, subject, html, text):
                channels.append("email")
    if pref.discord_enabled and pref.discord_webhook_url:
        if await _send_discord(pref.discord_webhook_url, title, description):
            channels.append("discord")
    if pref.push_enabled and pref.fcm_token:
        if await _send_push(pref.fcm_token, title, description.replace("**", "")):
            channels.append("push")

    if channels:
        db.add(NotificationDelivery(vehicle_id=vehicle.id, kind=kind, channels=",".join(channels)))
        await db.commit()
        logger.info("service_due_notified", vehicle_id=vehicle.id, kind=kind, channels=channels)


async def check_vehicle_notifications(db, vehicle_id: str) -> None:
    """Evaluate due triggers for one vehicle and send any new alerts."""
    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle:
        return
    prefs = list((await db.scalars(
        select(NotificationPreference).where(NotificationPreference.vehicle_id == vehicle_id)
    )).all())
    for pref in prefs:
        await _check_pref(db, pref, vehicle)


async def _check_pref(db, pref: NotificationPreference, vehicle: Vehicle) -> None:
    sent_kinds = set((await db.scalars(
        select(NotificationDelivery.kind).where(
            NotificationDelivery.vehicle_id == vehicle.id,
            NotificationDelivery.kind.in_(["service_due_days", "service_due_km", "fuel_gap"]),
        )
    )).all())

    # --- service due by days ---
    if "service_due_days" not in sent_kinds and pref.service_due_days and pref.service_due_days > 0:
        today = date.today()
        due_date = today + timedelta(days=pref.service_due_days)
        upcoming = list((await db.scalars(
            select(ServiceRecord).where(
                ServiceRecord.vehicle_id == vehicle.id,
                ServiceRecord.next_due_date.is_not(None),
                ServiceRecord.next_due_date <= due_date,
            ).order_by(ServiceRecord.next_due_date.asc())
        )).all())
        for svc in upcoming:
            days_left = (svc.next_due_date - today).days
            if days_left <= pref.service_due_days:
                await deliver_due_service(
                    db, pref, vehicle, svc, "service_due_days", float(days_left), [])
                break  # one alert per vehicle per kind

    # --- service due by km ---
    if "service_due_km" not in sent_kinds and pref.service_due_km and pref.service_due_km > 0:
        odo = vehicle.odometer_km or 0
        by_km = list((await db.scalars(
            select(ServiceRecord).where(
                ServiceRecord.vehicle_id == vehicle.id,
                ServiceRecord.next_due_km.is_not(None),
                ServiceRecord.next_due_km >= odo,
                ServiceRecord.next_due_km - odo <= pref.service_due_km,
            ).order_by(ServiceRecord.next_due_km.asc())
        )).all())
        for svc in by_km:
            km_left = svc.next_due_km - odo
            await deliver_due_service(
                db, pref, vehicle, svc, "service_due_km", float(km_left), [])
            break

    # --- fuel gap ---
    if "fuel_gap" not in sent_kinds and pref.fuel_gap_km and pref.fuel_gap_km > 0:
        from app.models.fuel import FuelLog
        last_fuel = await db.scalar(
            select(FuelLog).where(FuelLog.vehicle_id == vehicle.id)
            .order_by(FuelLog.odometer_km.desc())
        )
        odo = vehicle.odometer_km or 0
        if last_fuel and last_fuel.odometer_km and (odo - last_fuel.odometer_km) >= pref.fuel_gap_km:
            channels = []
            if pref.email_enabled:
                user = await db.get(User, pref.user_id)
                if user:
                    subject = f"{vehicle.nickname or vehicle.model or 'Vehicle'}: time to log fuel"
                    text = (f"Hi {user.display_name},\n\nThe odometer hasn't been logged in "
                            f"{(odo - last_fuel.odometer_km):,} km. Add a fuel fill to keep stats accurate.")
                    html = mail._branding(
                        f'<p style="color:#F5F7FA">Hi <b>{html.escape(user.display_name)}</b>,</p>'
                        f'<p style="color:#E5ECF5">{text.split(chr(10), 1)[1]}</p>'
                    )
                    if await _send_email(user.email, user.display_name, subject, html, text):
                        channels.append("email")
            if pref.discord_enabled and pref.discord_webhook_url:
                if await _send_discord(pref.discord_webhook_url, "Fuel log reminder", text):
                    channels.append("discord")
            if channels:
                db.add(NotificationDelivery(vehicle_id=vehicle.id, kind="fuel_gap",
                                            channels=",".join(channels)))
                await db.commit()
                logger.info("fuel_gap_notified", vehicle_id=vehicle.id)


# --- Scheduled + ad-hoc entry points (called from Celery / routers) ---------

def run_due_checks() -> None:
    """Called by Celery beat (daily) to re-evaluate all vehicles."""
    async def _run():
        async with SessionLocal() as db:
            vehicle_ids = list((await db.scalars(select(Vehicle.id))).all())
            for vid in vehicle_ids:
                await check_vehicle_notifications(db, vid)
    _run(_run())
