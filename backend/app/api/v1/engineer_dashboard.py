"""Engineer dashboard API (AUT-3663).

Endpoints:
- GET /engineers/dashboard — full dashboard summary
- GET /engineers/dashboard/requests — list incoming booking requests
- GET /engineers/dashboard/requests/{request_id} — request detail
- PATCH /engineers/dashboard/requests/{request_id} — respond to request
- GET /engineers/dashboard/certifications — list certifications
- POST /engineers/dashboard/certifications — add certification
- PATCH /engineers/dashboard/certifications/{cert_id} — update certification
- GET /engineers/dashboard/certifications/reminders — renewal reminders
- GET /engineers/dashboard/jobs — list completed jobs
- GET /engineers/dashboard/earnings — earnings summary
- GET /engineers/dashboard/earnings/by-type — earnings by job type
- GET /engineers/dashboard/earnings/by-period — earnings by period
- GET /engineers/dashboard/export — CSV export
"""

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.engineer_dashboard import (
    BookingRequestDetail,
    BookingRequestSummary,
    BookingRequestUpdate,
    CertificationCreate,
    CertificationSummary,
    CertificationUpdate,
    DashboardExport,
    EarningsByJobType,
    EarningsByPeriod,
    EarningsSummary,
    EngineerDashboard,
)
from app.services.engineer_dashboard import (
    export_certifications_csv,
    export_earnings_csv,
    export_requests_csv,
    get_booking_request_detail,
    get_dashboard_summary,
    get_engineer_booking_requests,
    get_engineer_certifications,
    get_engineer_jobs,
    get_engineer_earnings_by_type,
    get_earnings_by_period,
    get_earnings_summary,
    get_renewal_reminders,
    update_booking_request,
)

router = APIRouter(prefix="/engineers/dashboard", tags=["engineer-dashboard"])


async def _require_engineer_id(user: User = Depends(get_current_user)) -> str:
    """Get the engineer profile ID for the current user.

    Engineers are identified by their email matching the user's email.
    """
    from sqlalchemy import select
    from app.models.engineer import Engineer
    from app.db.session import get_db as _get_db
    import inspect

    # Get a fresh db session for this dependency
    db = None
    async for session in _get_db():
        db = session
        break

    if db is None:
        raise HTTPException(status_code=500, detail="Database unavailable")

    stmt = select(Engineer).where(Engineer.email == user.email)
    engineer = (await db.execute(stmt)).scalar_one_or_none()
    if not engineer:
        raise HTTPException(
            status_code=404,
            detail="Engineer profile not found. Create a profile first.",
        )
    return engineer.id


@router.get("", response_model=EngineerDashboard)
async def dashboard(
    engineer_id: str = Depends(_require_engineer_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Full engineer dashboard: requests, certifications, jobs, earnings."""
    data = await get_dashboard_summary(db, engineer_id)
    if not data:
        raise HTTPException(status_code=404, detail="Engineer not found")
    return data


@router.get("/requests", response_model=list[BookingRequestSummary])
async def list_requests(
    status: str | None = Query(
        None,
        description="Filter by status: pending/accepted/rejected/completed/cancelled",
    ),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    engineer_id: str = Depends(_require_engineer_id),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List incoming booking requests with pre-check reports."""
    results, _ = await get_engineer_booking_requests(
        db, engineer_id, status=status, page=page, limit=limit
    )
    return results


@router.get("/requests/{request_id}", response_model=BookingRequestDetail)
async def get_request(
    request_id: str,
    engineer_id: str = Depends(_require_engineer_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get booking request detail with pre-check report."""
    detail = await get_booking_request_detail(db, engineer_id, request_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Booking request not found")
    return detail


@router.patch("/requests/{request_id}", response_model=dict)
async def respond_to_request(
    request_id: str,
    payload: BookingRequestUpdate,
    engineer_id: str = Depends(_require_engineer_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Respond to a booking request (accept/reject/complete)."""
    updates = payload.model_dump(exclude_unset=True)
    result = await update_booking_request(db, engineer_id, request_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Booking request not found")
    return result


@router.get("/certifications", response_model=list[CertificationSummary])
async def list_certifications(
    status: str | None = Query(None, description="Filter: active/expired/expiring_soon"),
    engineer_id: str = Depends(_require_engineer_id),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List certifications with expiry dates."""
    return await get_engineer_certifications(db, engineer_id, status=status)


@router.post("/certifications", response_model=CertificationSummary, status_code=201)
async def add_certification(
    payload: CertificationCreate,
    engineer_id: str = Depends(_require_engineer_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Add a new certification."""
    from app.models.engineer import EngineerCertification
    import uuid

    cert = EngineerCertification(
        id=str(uuid.uuid4()),
        engineer_id=engineer_id,
        name=payload.name,
        issuer=payload.issuer,
        certification_number=payload.certification_number,
        category=payload.category,
        issued_date=payload.issued_date,
        expiry_date=payload.expiry_date,
        is_recurring=payload.is_recurring,
        renewal_period_months=payload.renewal_period_months,
    )
    db.add(cert)
    await db.commit()
    await db.refresh(cert)

    # Calculate days until expiry
    today = date.today()
    days_until = None
    if cert.expiry_date:
        days_until = (cert.expiry_date - today).days

    return {
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
    }


@router.patch("/certifications/{cert_id}", response_model=CertificationSummary)
async def update_certification(
    cert_id: str,
    payload: CertificationUpdate,
    engineer_id: str = Depends(_require_engineer_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update a certification."""
    from app.models.engineer import EngineerCertification
    from sqlalchemy import select

    stmt = select(EngineerCertification).where(
        EngineerCertification.id == cert_id,
        EngineerCertification.engineer_id == engineer_id,
    )
    cert = (await db.execute(stmt)).scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail="Certification not found")

    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if value is not None and hasattr(cert, key):
            setattr(cert, key, value)

    await db.commit()
    await db.refresh(cert)

    today = date.today()
    days_until = (cert.expiry_date - today).days if cert.expiry_date else None

    return {
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
    }


@router.get("/certifications/reminders", response_model=list[dict])
async def certification_reminders(
    remind_days: str = Query(
        default="90,30,7",
        description="Comma-separated days-before-expiry to check",
    ),
    engineer_id: str = Depends(_require_engineer_id),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Get certifications needing renewal attention."""
    try:
        days_list = [int(d.strip()) for d in remind_days.split(",")]
    except ValueError:
        days_list = [90, 30, 7]

    return await get_renewal_reminders(db, engineer_id, days_list)


@router.get("/jobs", response_model=list[dict])
async def list_jobs(
    payment_status: str | None = Query(None, description="Filter: pending/invoiced/paid"),
    service_type: str | None = Query(None, description="Filter by service type"),
    start_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    engineer_id: str = Depends(_require_engineer_id),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List completed jobs with earnings."""
    results, _ = await get_engineer_jobs(
        db, engineer_id,
        payment_status=payment_status,
        service_type=service_type,
        start_date=start_date,
        end_date=end_date,
        page=page, limit=limit,
    )
    return results


@router.get("/earnings", response_model=EarningsSummary)
async def earnings_summary(
    start_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    engineer_id: str = Depends(_require_engineer_id),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Earnings summary for a period."""
    return await get_earnings_summary(db, engineer_id, start_date=start_date, end_date=end_date)


@router.get("/earnings/by-type", response_model=list[EarningsByJobType])
async def earnings_by_type(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    engineer_id: str = Depends(_require_engineer_id),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Earnings breakdown by job/service type."""
    return await get_engineer_earnings_by_type(
        db, engineer_id, start_date=start_date, end_date=end_date
    )


@router.get("/earnings/by-period", response_model=list[EarningsByPeriod])
async def earnings_by_period(
    period: str = Query(
        "month",
        description="Period: day/week/month/quarter/year",
    ),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    engineer_id: str = Depends(_require_engineer_id),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Earnings tracking by period."""
    return await get_earnings_by_period(
        db, engineer_id, period=period, start_date=start_date, end_date=end_date
    )


@router.get("/export")
async def export_dashboard(
    export_type: str = Query(
        "earnings",
        description="Export type: earnings/certifications/requests/jobs",
    ),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    engineer_id: str = Depends(_require_engineer_id),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Export dashboard data as CSV."""
    from app.models.engineer import Engineer

    engineer = await db.get(Engineer, engineer_id)
    name = engineer.display_name if engineer else "Engineer"

    if export_type == "earnings":
        jobs, _ = await get_engineer_jobs(
            db, engineer_id, start_date=start_date, end_date=end_date, limit=10000
        )
        content = export_earnings_csv(jobs, name)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="engineer-earnings.csv"'},
        )
    elif export_type == "certifications":
        certs = await get_engineer_certifications(db, engineer_id)
        content = export_certifications_csv(certs, name)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="engineer-certifications.csv"'},
        )
    elif export_type == "requests":
        requests, _ = await get_engineer_booking_requests(
            db, engineer_id, limit=10000
        )
        content = export_requests_csv(requests, name)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="engineer-requests.csv"'},
        )
    elif export_type == "jobs":
        jobs, _ = await get_engineer_jobs(
            db, engineer_id, start_date=start_date, end_date=end_date, limit=10000
        )
        content = export_earnings_csv(jobs, name)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="engineer-jobs.csv"'},
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid export type")
