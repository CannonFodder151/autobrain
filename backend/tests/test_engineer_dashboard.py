"""Tests for engineer dashboard (AUT-3663).

Tests booking request listing, certifications, earnings aggregation, and CSV export
without requiring a live database — uses SQLAlchemy model construction with
mocked sessions where needed.
"""

import io
import csv
from datetime import date, datetime, time

import pytest

from app.schemas.engineer_dashboard import (
    BookingRequestUpdate,
    CertificationCreate,
    CertificationUpdate,
    EngineerDashboard,
    EarningsSummary,
)


def test_booking_request_update_schema() -> None:
    """BookingRequestUpdate accepts status changes."""
    update = BookingRequestUpdate(status="accepted", engineer_notes="Will service tomorrow")
    assert update.status == "accepted"
    assert update.engineer_notes == "Will service tomorrow"


def test_booking_request_update_status_none() -> None:
    """BookingRequestUpdate fields default to None."""
    update = BookingRequestUpdate()
    assert update.status is None
    assert update.engineer_notes is None
    assert update.quoted_price is None


def test_certification_create_schema() -> None:
    """CertificationCreate validates required fields."""
    cert = CertificationCreate(
        name="Advanced Engine Tuning",
        issuer="SAE International",
        certification_number="SAE-12345",
        category="mechanical",
        issued_date=date(2023, 1, 15),
        expiry_date=date(2026, 1, 15),
        is_recurring=True,
        renewal_period_months=12,
    )
    assert cert.name == "Advanced Engine Tuning"
    assert cert.issuer == "SAE International"
    assert cert.is_recurring is True
    assert cert.renewal_period_months == 12


def test_certification_create_minimal() -> None:
    """CertificationCreate accepts minimal required field (name only)."""
    cert = CertificationCreate(name="Basic Safety")
    assert cert.name == "Basic Safety"
    assert cert.issuer is None
    assert cert.is_recurring is False


def test_certification_update_schema() -> None:
    """CertificationUpdate allows partial updates."""
    update = CertificationUpdate(status="expired", expiry_date=date(2025, 1, 1))
    assert update.status == "expired"
    assert update.expiry_date == date(2025, 1, 1)


def test_engineer_dashboard_schema_defaults() -> None:
    """EngineerDashboard has sensible defaults."""
    dashboard = EngineerDashboard(
        engineer_id="eng-1",
        display_name="Jane Doe",
    )
    assert dashboard.pending_requests == 0
    assert dashboard.active_certifications == 0
    assert dashboard.completed_jobs == 0
    assert dashboard.total_earnings == 0.0
    assert dashboard.recent_requests == []
    assert dashboard.certifications == []


def test_earnings_summary_defaults() -> None:
    """EarningsSummary has correct defaults."""
    summary = EarningsSummary()
    assert summary.total_earnings == 0.0
    assert summary.total_jobs == 0
    assert summary.average_job_value == 0.0


def test_csv_export_earnings() -> None:
    """export_earnings_csv produces valid CSV content."""
    from app.services.engineer_dashboard import export_earnings_csv

    jobs = [
        {
            "completed_at": "2026-09-20T10:00:00",
            "service_type": "repair",
            "category": "brake",
            "user_name": "John Smith",
            "vehicle_make": "Toyota",
            "vehicle_model": "Corolla",
            "labour_total": 200.0,
            "parts_total": 150.0,
            "sublet_total": 0.0,
            "total_earnings": 350.0,
            "currency": "AUD",
            "payment_status": "paid",
            "paid_at": "2026-09-25T10:00:00",
        },
    ]
    content = export_earnings_csv(jobs, "Jane Doe")
    assert content.startswith(b"\xef\xbb\xbf")  # BOM
    text = content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    assert "AutoBrain Engineer Earnings" in rows[0][0]
    assert "Jane Doe" in rows[0][1]
    assert rows[2] == [
        "Date", "Service Type", "Category", "Customer", "Vehicle",
        "Labour", "Parts", "Sublet", "Total", "Payment Status", "Paid Date",
    ]
    assert rows[3][1] == "repair"
    assert rows[3][8] == "350.0"


def test_csv_export_certifications() -> None:
    """export_certifications_csv produces valid CSV content."""
    from app.services.engineer_dashboard import export_certifications_csv

    certs = [
        {
            "name": "ASE Master",
            "issuer": "ASE",
            "certification_number": "MT-123",
            "category": "mechanical",
            "issued_date": date(2022, 1, 1),
            "expiry_date": date(2025, 12, 31),
            "status": "active",
            "days_until_expiry": 100,
            "is_recurring": True,
        },
    ]
    content = export_certifications_csv(certs, "Jane Doe")
    text = content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    assert "AutoBrain Engineer Certifications" in rows[0][0]
    assert rows[3][0] == "ASE Master"
    assert rows[3][6] == "active"


def test_csv_export_requests() -> None:
    """export_requests_csv produces valid CSV content."""
    from app.services.engineer_dashboard import export_requests_csv

    requests = [
        {
            "created_at": "2026-09-20T10:00:00",
            "user_name": "John Smith",
            "vehicle_make": "Toyota",
            "vehicle_model": "Corolla",
            "service_type": "scheduled",
            "urgency": "normal",
            "preferred_date": date(2026, 9, 25),
            "status": "pending",
            "description": "Oil change",
        },
    ]
    content = export_requests_csv(requests, "Jane Doe")
    text = content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    assert "AutoBrain Engineer Booking Requests" in rows[0][0]
    assert rows[3][1] == "John Smith"  # Customer
    assert rows[3][3] == "scheduled"  # Service Type
    assert rows[3][6] == "pending"  # Status
