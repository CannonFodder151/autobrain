"""Engineer dashboard service (AUT-3663).

Aggregation queries for:
- Incoming booking requests with pre-check reports
- Active certifications with expiry dates and renewal reminders
- Completed jobs with earnings summary
- Earnings by period and job type
- CSV export
"""

import csv
import io
from datetime import date, datetime, time, timedelta
from dateutil.relativedelta import relativedelta
from typing import TYPE_CHECKING

from sqlalchemy import and_, case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.engineer import (
    Engineer,
    EngineerBookingRequest,
    EngineerCertification,
    EngineerJob,
)
from app.models.user import User
from app.models.vehicle import Vehicle

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


# --- Booking Requests ---


async def get_engineer_booking_requests(
    db: AsyncSession,
    engineer_id: str,
    status: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[dict], int]:
    """List incoming booking requests for an engineer, with user/vehicle info."""
    stmt = (
        select(EngineerBookingRequest)
        .options(
            selectinload(EngineerBookingRequest.user),
            selectinload(EngineerBookingRequest.vehicle),
        )
        .where(EngineerBookingRequest.engineer_id == engineer_id)
    )

    if status:
        stmt = stmt.where(EngineerBookingRequest.status == status)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(EngineerBookingRequest.created_at.desc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()

    results = []
    for req in rows:
        results.append({
            "id": req.id,
            "user_name": req.user.display_name if req.user else None,
            "vehicle_make": req.vehicle.make if req.vehicle else None,
            "vehicle_model": req.vehicle.model if req.vehicle else None,
            "vehicle_rego": req.vehicle.rego if req.vehicle else None,
            "service_type": req.service_type,
            "description": req.description,
            "preferred_date": req.preferred_date,
            "urgency": req.urgency,
            "status": req.status,
            "created_at": req.created_at.isoformat() if req.created_at else None,
            "symptoms": req.symptoms or [],
            "odometer_km": req.odometer_km,
        })

    return results, total


async def get_booking_request_detail(
    db: AsyncSession,
    engineer_id: str,
    request_id: str,
) -> dict | None:
    """Get full detail of a booking request."""
    stmt = (
        select(EngineerBookingRequest)
        .options(
            selectinload(EngineerBookingRequest.user),
            selectinload(EngineerBookingRequest.vehicle),
        )
        .where(
            EngineerBookingRequest.id == request_id,
            EngineerBookingRequest.engineer_id == engineer_id,
        )
    )
    req = (await db.execute(stmt)).scalar_one_or_none()
    if not req:
        return None

    return {
        "id": req.id,
        "user_name": req.user.display_name if req.user else None,
        "user_email": req.user.email if req.user else None,
        "user_phone": None,  # User model doesn't expose phone
        "vehicle_id": req.vehicle_id,
        "vehicle_make": req.vehicle.make if req.vehicle else None,
        "vehicle_model": req.vehicle.model if req.vehicle else None,
        "vehicle_rego": req.vehicle.rego if req.vehicle else None,
        "vehicle_year": req.vehicle.year if req.vehicle else None,
        "service_type": req.service_type,
        "description": req.description,
        "preferred_date": req.preferred_date,
        "preferred_time": str(req.preferred_time) if req.preferred_time else None,
        "urgency": req.urgency,
        "pre_check_report": req.pre_check_report,
        "symptoms": req.symptoms or [],
        "odometer_km": req.odometer_km,
        "status": req.status,
        "engineer_notes": req.engineer_notes,
        "quoted_price": req.quoted_price,
        "scheduled_date": req.scheduled_date,
        "scheduled_time": str(req.scheduled_time) if req.scheduled_time else None,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "updated_at": req.updated_at.isoformat() if req.updated_at else None,
        "responded_at": req.responded_at.isoformat() if req.responded_at else None,
        "completed_at": req.completed_at.isoformat() if req.completed_at else None,
    }


async def update_booking_request(
    db: AsyncSession,
    engineer_id: str,
    request_id: str,
    updates: dict,
) -> dict | None:
    """Update a booking request (accept/reject/respond)."""
    stmt = select(EngineerBookingRequest).where(
        EngineerBookingRequest.id == request_id,
        EngineerBookingRequest.engineer_id == engineer_id,
    )
    req = (await db.execute(stmt)).scalar_one_or_none()
    if not req:
        return None

    for key, value in updates.items():
        if value is not None and hasattr(req, key):
            setattr(req, key, value)

    # Track response time
    if req.responded_at is None and req.status in ("accepted", "rejected"):
        req.responded_at = datetime.utcnow()

    # Track completion time
    if req.status == "completed" and req.completed_at is None:
        req.completed_at = datetime.utcnow()

    await db.commit()
    await db.refresh(req)
    return {"id": req.id, "status": req.status}


# --- Owner-facing Booking Requests (AUT-3662) ---

async def create_booking_request(
    db: AsyncSession,
    user_id: str,
    vehicle_id: str,
    engineer_id: str,
    payload: dict,
) -> dict | None:
    """Create a booking request from owner to engineer.

    Generates a pre-check report from vehicle + mods data if requested.
    """
    # Verify engineer exists and is active
    stmt = select(Engineer).where(Engineer.id == engineer_id, Engineer.is_active.is_(True))
    engineer = (await db.execute(stmt)).scalar_one_or_none()
    if not engineer:
        return None

    # Verify vehicle belongs to user
    stmt = select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.user_id == user_id)
    vehicle = (await db.execute(stmt)).scalar_one_or_none()
    if not vehicle:
        return None

    # Build pre-check report from vehicle data + mods + symptoms
    pre_check_report = None
    if payload.get("auto_generate_precheck", True):
        pre_check_report = _generate_precheck_report(vehicle, payload)

    # Parse preferred_time if provided
    preferred_time = payload.get("preferred_time")
    if preferred_time:
        try:
            parts = preferred_time.split(":")
            preferred_time = time(int(parts[0]), int(parts[1]))
        except (ValueError, IndexError):
            preferred_time = None

    req = EngineerBookingRequest(
        engineer_id=engineer_id,
        user_id=user_id,
        vehicle_id=vehicle_id,
        service_type=payload.get("service_type", "repair"),
        description=payload.get("description"),
        preferred_date=payload.get("preferred_date"),
        preferred_time=preferred_time,
        urgency=payload.get("urgency", "normal"),
        symptoms=payload.get("symptoms", []),
        odometer_km=payload.get("odometer_km"),
        pre_check_report=pre_check_report,
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return {
        "id": req.id,
        "engineer_id": req.engineer_id,
        "user_id": req.user_id,
        "vehicle_id": req.vehicle_id,
        "service_type": req.service_type,
        "status": req.status,
        "created_at": req.created_at.isoformat() if req.created_at else None,
    }


def _generate_precheck_report(vehicle: Vehicle, payload: dict) -> dict:
    """Generate a deterministic pre-check report from vehicle + mods data.

    This is a deterministic fallback; AI enhancement can be added later.
    """
    mods = payload.get("mods", [])
    symptoms = payload.get("symptoms", [])
    odometer = payload.get("odometer_km") or vehicle.odometer_km or 0

    # Build report sections
    report = {
        "generated_at": datetime.utcnow().isoformat(),
        "vehicle": {
            "make": vehicle.make,
            "model": vehicle.model,
            "year": vehicle.year,
            "engine": vehicle.engine,
            "transmission": vehicle.transmission,
            "odometer_km": odometer,
            "vin": vehicle.vin,
        },
        "modifications": mods,
        "symptoms": symptoms,
        "service_context": {
            "service_type": payload.get("service_type", "repair"),
            "urgency": payload.get("urgency", "normal"),
        },
        "checks": [],
        "recommendations": [],
        "warnings": [],
    }

    # Add odometer-based checks
    if odometer > 100000:
        report["checks"].append({
            "item": "High mileage service",
            "status": "due",
            "detail": f"Odometer at {odometer:,} km — major service interval likely due",
        })
    elif odometer > 50000:
        report["checks"].append({
            "item": "Mid-life service review",
            "status": "review",
            "detail": f"Odometer at {odometer:,} km — check belts, fluids, brake wear",
        })

    # Add mod-specific checks
    mod_keywords = [m.lower() for m in mods]
    if any("turbo" in m or "supercharger" in m for m in mod_keywords):
        report["checks"].append({
            "item": "Forced induction system",
            "status": "inspect",
            "detail": "Check boost leaks, intercooler, oil feed/return lines, wastegate operation",
        })
        report["recommendations"].append("Verify boost pressure holds under load")

    if any("ecu" in m or "tune" in m or "remap" in m for m in mod_keywords):
        report["checks"].append({
            "item": "ECU tune / remap",
            "status": "verify",
            "detail": "Confirm tune matches current hardware; check for lean conditions under load",
        })
        report["warnings"].append("Aftermarket tune may void manufacturer warranty")

    if any("suspension" in m or "coilover" in m or "lowering" in m for m in mod_keywords):
        report["checks"].append({
            "item": "Modified suspension",
            "status": "inspect",
            "detail": "Check alignment, strut tops, bushings, ride height compliance",
        })

    if any("brake" in m for m in mod_keywords):
        report["checks"].append({
            "item": "Upgraded brakes",
            "status": "inspect",
            "detail": "Check pad/rotor wear, fluid condition, caliper function",
        })

    if any("exhaust" in m for m in mod_keywords):
        report["checks"].append({
            "item": "Aftermarket exhaust",
            "status": "inspect",
            "detail": "Check for leaks, compliance with noise regulations, catalyst presence",
        })

    # Symptom-based recommendations
    for symptom in symptoms:
        sl = symptom.lower()
        if "noise" in sl or "knock" in sl or "rattle" in sl:
            report["recommendations"].append(
                f"Investigate noise: {symptom} — check engine mounts, exhaust, suspension"
            )
        elif "vibration" in sl or "shake" in sl:
            report["recommendations"].append(
                f"Investigate vibration: {symptom} — check wheels, tires, driveshaft, engine mounts"
            )
        elif "overheat" in sl or "hot" in sl or "temp" in sl:
            report["recommendations"].append(
                f"Investigate overheating: {symptom} — check coolant, thermostat, radiator, water pump"
            )
        elif "smoke" in sl:
            report["recommendations"].append(
                f"Investigate smoke: {symptom} — check oil consumption, turbo seals, head gasket"
            )
        elif "light" in sl or "check engine" in sl or "cel" in sl or "mil" in sl:
            report["recommendations"].append(
                f"Read fault codes for: {symptom} — diagnostic scan required"
            )
        elif "brake" in sl:
            report["recommendations"].append(
                f"Brake system check for: {symptom} — pads, rotors, fluid, lines"
            )

    if not report["checks"]:
        report["checks"].append({
            "item": "General inspection",
            "status": "ok",
            "detail": "No specific automated checks triggered — general inspection recommended",
        })

    return report


async def get_owner_booking_requests(
    db: AsyncSession,
    user_id: str,
    status: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[dict], int]:
    """List booking requests submitted by the owner (across all their vehicles)."""
    stmt = (
        select(EngineerBookingRequest)
        .options(
            selectinload(EngineerBookingRequest.engineer),
            selectinload(EngineerBookingRequest.vehicle),
        )
        .where(EngineerBookingRequest.user_id == user_id)
    )

    if status:
        stmt = stmt.where(EngineerBookingRequest.status == status)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(EngineerBookingRequest.created_at.desc())
    stmt = stmt.offset((page - 1) * limit).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()

    results = []
    for req in rows:
        results.append({
            "id": req.id,
            "engineer_id": req.engineer_id,
            "engineer_name": req.engineer.display_name if req.engineer else None,
            "engineer_rating": req.engineer.rating if req.engineer else None,
            "engineer_phone": req.engineer.phone if req.engineer else None,
            "vehicle_id": req.vehicle_id,
            "vehicle_make": req.vehicle.make if req.vehicle else None,
            "vehicle_model": req.vehicle.model if req.vehicle else None,
            "vehicle_rego": req.vehicle.rego if req.vehicle else None,
            "service_type": req.service_type,
            "description": req.description,
            "preferred_date": req.preferred_date,
            "preferred_time": str(req.preferred_time) if req.preferred_time else None,
            "urgency": req.urgency,
            "status": req.status,
            "created_at": req.created_at.isoformat() if req.created_at else None,
            "responded_at": req.responded_at.isoformat() if req.responded_at else None,
            "engineer_notes": req.engineer_notes,
            "quoted_price": req.quoted_price,
            "scheduled_date": req.scheduled_date,
            "scheduled_time": str(req.scheduled_time) if req.scheduled_time else None,
        })

    return results, total


async def get_booking_request_for_owner(
    db: AsyncSession,
    user_id: str,
    request_id: str,
) -> dict | None:
    """Get full detail of a booking request for the owner."""
    stmt = (
        select(EngineerBookingRequest)
        .options(
            selectinload(EngineerBookingRequest.engineer),
            selectinload(EngineerBookingRequest.vehicle),
        )
        .where(
            EngineerBookingRequest.id == request_id,
            EngineerBookingRequest.user_id == user_id,
        )
    )
    req = (await db.execute(stmt)).scalar_one_or_none()
    if not req:
        return None

    return {
        "id": req.id,
        "engineer_id": req.engineer_id,
        "engineer_name": req.engineer.display_name if req.engineer else None,
        "engineer_rating": req.engineer.rating if req.engineer else None,
        "engineer_phone": req.engineer.phone if req.engineer else None,
        "engineer_email": req.engineer.email if req.engineer else None,
        "engineer_specialties": req.engineer.specialties if req.engineer else [],
        "engineer_years_experience": req.engineer.years_experience if req.engineer else None,
        "vehicle_id": req.vehicle_id,
        "vehicle_make": req.vehicle.make if req.vehicle else None,
        "vehicle_model": req.vehicle.model if req.vehicle else None,
        "vehicle_rego": req.vehicle.rego if req.vehicle else None,
        "vehicle_year": req.vehicle.year if req.vehicle else None,
        "vehicle_nickname": req.vehicle.nickname if req.vehicle else None,
        "service_type": req.service_type,
        "description": req.description,
        "preferred_date": req.preferred_date,
        "preferred_time": str(req.preferred_time) if req.preferred_time else None,
        "urgency": req.urgency,
        "pre_check_report": req.pre_check_report,
        "symptoms": req.symptoms or [],
        "mods": [],  # Mods are not stored separately; could be extracted from pre_check_report
        "odometer_km": req.odometer_km,
        "status": req.status,
        "engineer_notes": req.engineer_notes,
        "quoted_price": req.quoted_price,
        "scheduled_date": req.scheduled_date,
        "scheduled_time": str(req.scheduled_time) if req.scheduled_time else None,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "updated_at": req.updated_at.isoformat() if req.updated_at else None,
        "responded_at": req.responded_at.isoformat() if req.responded_at else None,
        "completed_at": req.completed_at.isoformat() if req.completed_at else None,
    }


async def cancel_booking_request(
    db: AsyncSession,
    user_id: str,
    request_id: str,
) -> dict | None:
    """Cancel a booking request (owner can only cancel if still pending)."""
    stmt = select(EngineerBookingRequest).where(
        EngineerBookingRequest.id == request_id,
        EngineerBookingRequest.user_id == user_id,
        EngineerBookingRequest.status == "pending",
    )
    req = (await db.execute(stmt)).scalar_one_or_none()
    if not req:
        return None

    req.status = "cancelled"
    await db.commit()
    await db.refresh(req)
    return {"id": req.id, "status": req.status}


async def notify_engineer_booking_request(
    db: AsyncSession,
    engineer_id: str,
    payload: dict,
) -> None:
    """Notify engineer of a new booking request via email/push/Discord.

    Uses the engineer's contact info (email, phone for future SMS, Discord webhook
    if configured on their user account). For now, we log and create a notification
    delivery record. Full multi-channel delivery can be expanded later.
    """
    from app.models.engineer import Engineer
    from app.models.notification import NotificationDelivery
    from app.models.user import User
    from datetime import datetime

    engineer = await db.get(Engineer, engineer_id)
    if not engineer:
        return

    # Try to find a linked User account for the engineer (by email)
    user = await db.scalar(select(User).where(User.email == engineer.email))

    # Create a notification delivery record for tracking
    delivery = NotificationDelivery(
        user_id=user.id if user else None,
        vehicle_id=None,
        kind=f"booking_request:{payload.get('service_type', 'repair')}",
        channels="email",  # Default to email
        sent_at=datetime.utcnow(),
    )
    db.add(delivery)
    await db.commit()

    # TODO: Send actual notification via email/push/Discord
    # This can be expanded to use the notify.py service or a new engineer_notifications.py
    logger.info(
        "booking_request_notification_queued",
        engineer_id=engineer_id,
        service_type=payload.get("service_type"),
        user_id=user.id if user else None,
    )


# --- Certifications ---


async def get_engineer_certifications(
    db: AsyncSession,
    engineer_id: str,
    status: str | None = None,
) -> list[dict]:
    """List certifications for an engineer, with days-until-expiry."""
    today = date.today()
    stmt = select(EngineerCertification).where(
        EngineerCertification.engineer_id == engineer_id
    )

    if status:
        stmt = stmt.where(EngineerCertification.status == status)

    stmt = stmt.order_by(EngineerCertification.expiry_date.asc().nullslast())
    rows = (await db.execute(stmt)).scalars().all()

    results = []
    for cert in rows:
        days_until = None
        if cert.expiry_date:
            days_until = (cert.expiry_date - today).days

        results.append({
            "id": cert.id,
            "name": cert.name,
            "issuer": cert.issuer,
            "certification_number": cert.certification_number,
            "category": cert.category,
            "issued_date": cert.issued_date,
            "expiry_date": cert.expiry_date,
            "status": cert.status,
            "days_until_expiry": days_until,
            "is_recurring": cert.is_recurring,
        })

    return results


async def get_renewal_reminders(
    db: AsyncSession,
    engineer_id: str,
    remind_days: list[int] | None = None,
) -> list[dict]:
    """Get certifications needing renewal attention (expiring within N days)."""
    if remind_days is None:
        remind_days = [90, 30, 7]

    today = date.today()
    results = []

    for days in remind_days:
        target_date = today + timedelta(days=days)
        stmt = select(EngineerCertification).where(
            EngineerCertification.engineer_id == engineer_id,
            EngineerCertification.expiry_date.isnot(None),
            EngineerCertification.expiry_date <= target_date,
            EngineerCertification.expiry_date >= today,
        )
        rows = (await db.execute(stmt)).scalars().all()
        for cert in rows:
            days_until = (cert.expiry_date - today).days if cert.expiry_date else None
            results.append({
                "id": cert.id,
                "name": cert.name,
                "issuer": cert.issuer,
                "expiry_date": cert.expiry_date,
                "days_until_expiry": days_until,
                "reminder_days": days,
                "status": cert.status,
            })

    return results


# --- Jobs & Earnings ---


async def get_engineer_jobs(
    db: AsyncSession,
    engineer_id: str,
    payment_status: str | None = None,
    service_type: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[dict], int]:
    """List completed jobs for an engineer, with user/vehicle info."""
    stmt = (
        select(EngineerJob)
        .options(
            selectinload(EngineerJob.user),
            selectinload(EngineerJob.vehicle),
        )
        .where(EngineerJob.engineer_id == engineer_id)
    )

    if payment_status:
        stmt = stmt.where(EngineerJob.payment_status == payment_status)
    if service_type:
        stmt = stmt.where(EngineerJob.service_type == service_type)
    if start_date:
        stmt = stmt.where(EngineerJob.completed_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        stmt = stmt.where(EngineerJob.completed_at <= datetime.combine(end_date, datetime.max.time()))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(EngineerJob.completed_at.desc().nullslast())
    stmt = stmt.offset((page - 1) * limit).limit(limit)

    rows = (await db.execute(stmt)).scalars().all()

    results = []
    for job in rows:
        results.append({
            "id": job.id,
            "user_name": job.user.display_name if job.user else None,
            "vehicle_make": job.vehicle.make if job.vehicle else None,
            "vehicle_model": job.vehicle.model if job.vehicle else None,
            "vehicle_rego": job.vehicle.rego if job.vehicle else None,
            "service_type": job.service_type,
            "category": job.category,
            "description": job.description,
            "labour_total": job.labour_total,
            "parts_total": job.parts_total,
            "sublet_total": job.sublet_total,
            "total_earnings": job.total_earnings,
            "currency": job.currency,
            "payment_status": job.payment_status,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "paid_at": job.paid_at.isoformat() if job.paid_at else None,
        })

    return results, total


async def get_earnings_summary(
    db: AsyncSession,
    engineer_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """Aggregate earnings summary for an engineer."""
    stmt = select(EngineerJob).where(EngineerJob.engineer_id == engineer_id)

    if start_date:
        stmt = stmt.where(EngineerJob.completed_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        stmt = stmt.where(EngineerJob.completed_at <= datetime.combine(end_date, datetime.max.time()))

    rows = (await db.execute(stmt)).scalars().all()

    total_earnings = 0.0
    labour_earnings = 0.0
    parts_earnings = 0.0
    sublet_earnings = 0.0
    paid_count = 0
    pending_count = 0
    invoiced_count = 0

    for job in rows:
        total_earnings += job.total_earnings
        labour_earnings += job.labour_total
        parts_earnings += job.parts_total
        sublet_earnings += job.sublet_total
        if job.payment_status == "paid":
            paid_count += 1
        elif job.payment_status == "pending":
            pending_count += 1
        elif job.payment_status == "invoiced":
            invoiced_count += 1

    total_jobs = len(rows)

    return {
        "total_earnings": round(total_earnings, 2),
        "total_jobs": total_jobs,
        "average_job_value": round(total_earnings / total_jobs, 2) if total_jobs > 0 else 0.0,
        "labour_earnings": round(labour_earnings, 2),
        "parts_earnings": round(parts_earnings, 2),
        "sublet_earnings": round(sublet_earnings, 2),
        "paid_count": paid_count,
        "pending_count": pending_count,
        "invoiced_count": invoiced_count,
    }


async def get_earnings_by_type(
    db: AsyncSession,
    engineer_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    """Earnings breakdown by service/job type."""
    stmt = select(EngineerJob).where(EngineerJob.engineer_id == engineer_id)

    if start_date:
        stmt = stmt.where(EngineerJob.completed_at >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        stmt = stmt.where(EngineerJob.completed_at <= datetime.combine(end_date, datetime.max.time()))

    rows = (await db.execute(stmt)).scalars().all()

    # Aggregate by service_type
    by_type: dict[str, dict] = {}
    for job in rows:
        key = job.service_type
        if key not in by_type:
            by_type[key] = {
                "service_type": key,
                "job_count": 0,
                "total_earnings": 0.0,
                "labour_total": 0.0,
                "parts_total": 0.0,
            }
        by_type[key]["job_count"] += 1
        by_type[key]["total_earnings"] += job.total_earnings
        by_type[key]["labour_total"] += job.labour_total
        by_type[key]["parts_total"] += job.parts_total

    # Calculate averages and round
    results = []
    for data in by_type.values():
        data["total_earnings"] = round(data["total_earnings"], 2)
        data["labour_total"] = round(data["labour_total"], 2)
        data["parts_total"] = round(data["parts_total"], 2)
        data["average_earnings"] = round(
            data["total_earnings"] / data["job_count"], 2
        ) if data["job_count"] > 0 else 0.0
        results.append(data)

    # Sort by total earnings descending
    results.sort(key=lambda x: x["total_earnings"], reverse=True)
    return results


async def get_earnings_by_period(
    db: AsyncSession,
    engineer_id: str,
    period: str = "month",
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    """Earnings tracking by period (day/week/month/quarter/year)."""
    today = date.today()

    if start_date is None:
        if period == "day":
            start_date = today - timedelta(days=30)
        elif period == "week":
            start_date = today - timedelta(weeks=12)
        elif period == "month":
            start_date = today - relativedelta(months=12)
        elif period == "quarter":
            start_date = today - relativedelta(months=24)
        elif period == "year":
            start_date = today - relativedelta(years=3)
        else:
            start_date = today - relativedelta(months=12)

    if end_date is None:
        end_date = today

    stmt = select(EngineerJob).where(
        EngineerJob.engineer_id == engineer_id,
        EngineerJob.completed_at.isnot(None),
        EngineerJob.completed_at >= datetime.combine(start_date, datetime.min.time()),
        EngineerJob.completed_at <= datetime.combine(end_date, datetime.max.time()),
    )
    rows = (await db.execute(stmt)).scalars().all()

    # Group by period
    by_period: dict[str, dict] = {}
    for job in rows:
        if not job.completed_at:
            continue
        if period == "day":
            key = job.completed_at.strftime("%Y-%m-%d")
        elif period == "week":
            key = f"{job.completed_at.isocalendar()[0]}-W{job.completed_at.isocalendar()[1]:02d}"
        elif period == "month":
            key = job.completed_at.strftime("%Y-%m")
        elif period == "quarter":
            q = (job.completed_at.month - 1) // 3 + 1
            key = f"{job.completed_at.year}-Q{q}"
        elif period == "year":
            key = str(job.completed_at.year)
        else:
            key = job.completed_at.strftime("%Y-%m")

        if key not in by_period:
            by_period[key] = {"period": key, "total_earnings": 0.0, "job_count": 0}
        by_period[key]["total_earnings"] += job.total_earnings
        by_period[key]["job_count"] += 1

    results = sorted(by_period.values(), key=lambda x: x["period"])
    for r in results:
        r["total_earnings"] = round(r["total_earnings"], 2)
    return results


async def get_engineer_earnings_by_type(
    db: AsyncSession,
    engineer_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[dict]:
    """Alias for get_earnings_by_type (used by dashboard endpoint)."""
    return await get_earnings_by_type(db, engineer_id, start_date, end_date)


async def get_dashboard_summary(db: AsyncSession, engineer_id: str) -> dict:
    """Aggregate all dashboard sections into a single response."""
    today = date.today()
    month_start = today.replace(day=1)
    last_month_start = (month_start - relativedelta(months=1)).replace(day=1)
    year_start = today.replace(month=1, day=1)

    # Engineer info
    eng = await db.get(Engineer, engineer_id)
    if not eng:
        return {}

    # Pending requests count
    pending_count = (
        await db.execute(
            select(func.count()).select_from(EngineerBookingRequest).where(
                EngineerBookingRequest.engineer_id == engineer_id,
                EngineerBookingRequest.status == "pending",
            )
        )
    ).scalar_one()

    # Recent requests (last 10)
    recent_requests, _ = await get_engineer_booking_requests(
        db, engineer_id, page=1, limit=10
    )

    # Certifications
    all_certs = await get_engineer_certifications(db, engineer_id)
    active_certs = [c for c in all_certs if c["status"] == "active"]
    expiring_certs = [c for c in all_certs if c["status"] == "active" and c["days_until_expiry"] is not None and c["days_until_expiry"] <= 30 and c["days_until_expiry"] >= 0]
    expired_certs = [c for c in all_certs if c["status"] == "expired"]
    renewal_reminders = await get_renewal_reminders(db, engineer_id)

    # Jobs & earnings
    total_jobs_count = (
        await db.execute(
            select(func.count()).select_from(EngineerJob).where(
                EngineerJob.engineer_id == engineer_id
            )
        )
    ).scalar_one()

    # Earnings summaries
    all_time_earnings = await get_earnings_summary(db, engineer_id)
    this_month_earnings = await get_earnings_summary(db, engineer_id, start_date=month_start)
    last_month_earnings_data = await get_earnings_summary(db, engineer_id, start_date=last_month_start, end_date=month_start - timedelta(days=1))
    ytd_earnings = await get_earnings_summary(db, engineer_id, start_date=year_start)

    # Earnings by type
    earnings_by_type = await get_earnings_by_type(db, engineer_id)

    # Earnings by month (last 12)
    earnings_by_month = await get_earnings_by_period(db, engineer_id, period="month")

    # Recent jobs (last 10)
    recent_jobs, _ = await get_engineer_jobs(db, engineer_id, page=1, limit=10)

    return {
        "engineer_id": eng.id,
        "display_name": eng.display_name,
        "pending_requests": pending_count,
        "recent_requests": recent_requests,
        "active_certifications": len(active_certs),
        "expiring_certifications": len(expiring_certs),
        "expired_certifications": len(expired_certs),
        "certifications": all_certs,
        "renewal_reminders": renewal_reminders,
        "completed_jobs": total_jobs_count,
        "total_earnings": all_time_earnings["total_earnings"],
        "recent_jobs": recent_jobs,
        "earnings_summary": all_time_earnings,
        "earnings_by_type": earnings_by_type,
        "earnings_by_period": earnings_by_month,
        "this_month_earnings": this_month_earnings["total_earnings"],
        "last_month_earnings": last_month_earnings_data["total_earnings"],
        "year_to_date_earnings": ytd_earnings["total_earnings"],
    }


# --- CSV Export ---


def export_earnings_csv(jobs: list[dict], engineer_name: str) -> bytes:
    """Export earnings/jobs to CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["AutoBrain Engineer Earnings", engineer_name])
    writer.writerow([])
    writer.writerow([
        "Date", "Service Type", "Category", "Customer", "Vehicle",
        "Labour", "Parts", "Sublet", "Total", "Payment Status", "Paid Date",
    ])
    for job in jobs:
        vehicle = f"{job.get('vehicle_make', '')} {job.get('vehicle_model', '')}".strip()
        writer.writerow([
            job.get("completed_at", ""),
            job.get("service_type", ""),
            job.get("category", ""),
            job.get("user_name", ""),
            vehicle,
            job.get("labour_total", 0),
            job.get("parts_total", 0),
            job.get("sublet_total", 0),
            job.get("total_earnings", 0),
            job.get("payment_status", ""),
            job.get("paid_at", ""),
        ])
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def export_certifications_csv(certs: list[dict], engineer_name: str) -> bytes:
    """Export certifications to CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["AutoBrain Engineer Certifications", engineer_name])
    writer.writerow([])
    writer.writerow([
        "Name", "Issuer", "Cert Number", "Category", "Issued", "Expiry",
        "Status", "Days Until Expiry", "Recurring",
    ])
    for cert in certs:
        writer.writerow([
            cert.get("name", ""),
            cert.get("issuer", ""),
            cert.get("certification_number", ""),
            cert.get("category", ""),
            cert.get("issued_date", ""),
            cert.get("expiry_date", ""),
            cert.get("status", ""),
            cert.get("days_until_expiry", ""),
            "Yes" if cert.get("is_recurring") else "No",
        ])
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def export_requests_csv(requests: list[dict], engineer_name: str) -> bytes:
    """Export booking requests to CSV."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["AutoBrain Engineer Booking Requests", engineer_name])
    writer.writerow([])
    writer.writerow([
        "Date", "Customer", "Vehicle", "Service Type", "Urgency",
        "Preferred Date", "Status", "Description",
    ])
    for req in requests:
        vehicle = f"{req.get('vehicle_make', '')} {req.get('vehicle_model', '')}".strip()
        writer.writerow([
            req.get("created_at", ""),
            req.get("user_name", ""),
            vehicle,
            req.get("service_type", ""),
            req.get("urgency", ""),
            req.get("preferred_date", ""),
            req.get("status", ""),
            req.get("description", ""),
        ])
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")
