"""AUT-3170: DiagnosticOut must expose status + resolved_at.

The demo seed writes each vehicle's second diagnostic with
status="resolved" + a resolved_at timestamp, but DiagnosticOut previously
omitted both fields, so GET /vehicles/{id}/diagnostics returned entries with
no way to tell open from resolved (open=2, resolved=0). This test pins the
schema so the fix cannot regress.
"""

from datetime import datetime, timezone

from app.schemas.diagnostic import DiagnosticOut


def _row(status: str, resolved_at: datetime | None) -> dict:
    return {
        "id": "diag-1",
        "vehicle_id": "veh-1",
        "symptoms": "engine knock",
        "ai_response": "{}",
        "summary": "knock",
        "severity": "medium",
        "estimated_cost": 123.0,
        "parts_needed": None,
        "added_to_service": False,
        "linked_service_id": None,
        "status": status,
        "resolved_at": resolved_at,
        "created_at": datetime.now(timezone.utc),
    }


def test_diagnostic_out_exposes_status_and_resolved_at() -> None:
    fields = set(DiagnosticOut.model_fields.keys())
    assert "status" in fields
    assert "resolved_at" in fields


def test_diagnostic_out_open_entry() -> None:
    m = DiagnosticOut.model_validate(_row("open", None))
    assert m.status == "open"
    assert m.resolved_at is None


def test_diagnostic_out_resolved_entry() -> None:
    ts = datetime.now(timezone.utc)
    m = DiagnosticOut.model_validate(_row("resolved", ts))
    assert m.status == "resolved"
    assert m.resolved_at == ts


def test_diagnostic_out_open_and_resolved_distinct() -> None:
    """AC6: open + resolved entries must be distinguishable."""
    open_row = DiagnosticOut.model_validate(_row("open", None))
    resolved_row = DiagnosticOut.model_validate(_row("resolved", datetime.now(timezone.utc)))
    assert open_row.status != resolved_row.status
    assert open_row.resolved_at is None
    assert resolved_row.resolved_at is not None