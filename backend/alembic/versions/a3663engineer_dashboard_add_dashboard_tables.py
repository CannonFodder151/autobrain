"""add engineer dashboard tables (AUT-3663)

Booking requests, certifications with expiry tracking, and completed jobs
with earnings breakdown for the engineer dashboard.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "a3663engineer_dashboard"
down_revision: Union[str, None] = "z2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _online() -> bool:
    return not context.is_offline_mode()


def _has_table(name: str) -> bool:
    if not _online():
        return False
    insp = sa.inspect(op.get_bind())
    return name in insp.get_table_names()


def upgrade() -> None:
    # engineer_booking_requests
    if not _has_table("engineer_booking_requests"):
        op.create_table(
            "engineer_booking_requests",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "engineer_id", sa.String(36), sa.ForeignKey("engineers.id"), nullable=False
            ),
            sa.Column(
                "user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False
            ),
            sa.Column(
                "vehicle_id", sa.String(36), sa.ForeignKey("vehicles.id"), nullable=False
            ),
            sa.Column("service_type", sa.String(60), nullable=False),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("preferred_date", sa.Date, nullable=True),
            sa.Column("preferred_time", sa.Time, nullable=True),
            sa.Column("urgency", sa.String(20), nullable=False, server_default="normal"),
            sa.Column("pre_check_report", JSONB, nullable=True),
            sa.Column("symptoms", JSONB, nullable=False, server_default="[]"),
            sa.Column("odometer_km", sa.Integer, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("engineer_notes", sa.Text, nullable=True),
            sa.Column("quoted_price", sa.Float, nullable=True),
            sa.Column("scheduled_date", sa.Date, nullable=True),
            sa.Column("scheduled_time", sa.Time, nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=False,
            ),
            sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_booking_requests_engineer_status",
            "engineer_booking_requests",
            ["engineer_id", "status"],
        )
        op.create_index(
            "ix_booking_requests_user_status",
            "engineer_booking_requests",
            ["user_id", "status"],
        )
        op.create_index(
            "ix_booking_requests_created",
            "engineer_booking_requests",
            ["created_at"],
        )

    # engineer_certifications
    if not _has_table("engineer_certifications"):
        op.create_table(
            "engineer_certifications",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "engineer_id", sa.String(36), sa.ForeignKey("engineers.id"), nullable=False
            ),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("issuer", sa.String(200), nullable=True),
            sa.Column("certification_number", sa.String(100), nullable=True),
            sa.Column("category", sa.String(60), nullable=True),
            sa.Column("issued_date", sa.Date, nullable=True),
            sa.Column("expiry_date", sa.Date, nullable=True),
            sa.Column("is_recurring", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("renewal_period_months", sa.Integer, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("reminder_sent_90", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("reminder_sent_30", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("reminder_sent_7", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("reminder_sent_expired", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("document_key", sa.String(512), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_certifications_engineer_expiry",
            "engineer_certifications",
            ["engineer_id", "expiry_date"],
        )
        op.create_index(
            "ix_certifications_engineer_status",
            "engineer_certifications",
            ["engineer_id", "status"],
        )

    # engineer_jobs
    if not _has_table("engineer_jobs"):
        op.create_table(
            "engineer_jobs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "engineer_id", sa.String(36), sa.ForeignKey("engineers.id"), nullable=False
            ),
            sa.Column(
                "booking_request_id",
                sa.String(36),
                sa.ForeignKey("engineer_booking_requests.id"),
                nullable=True,
            ),
            sa.Column(
                "user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False
            ),
            sa.Column(
                "vehicle_id", sa.String(36), sa.ForeignKey("vehicles.id"), nullable=False
            ),
            sa.Column("service_type", sa.String(60), nullable=False),
            sa.Column("category", sa.String(60), nullable=True),
            sa.Column("description", sa.Text, nullable=True),
            sa.Column("work_performed", sa.Text, nullable=True),
            sa.Column("labour_hours", sa.Float, nullable=True),
            sa.Column("labour_rate", sa.Float, nullable=True),
            sa.Column("labour_total", sa.Float, nullable=False, server_default="0"),
            sa.Column("parts_total", sa.Float, nullable=False, server_default="0"),
            sa.Column("sublet_total", sa.Float, nullable=False, server_default="0"),
            sa.Column("discount", sa.Float, nullable=False, server_default="0"),
            sa.Column("tax", sa.Float, nullable=False, server_default="0"),
            sa.Column("total_earnings", sa.Float, nullable=False, server_default="0"),
            sa.Column("currency", sa.String(8), nullable=False, server_default="AUD"),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("invoiced_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "payment_status", sa.String(20), nullable=False, server_default="pending"
            ),
            sa.Column("parts_used", JSONB, nullable=False, server_default="[]"),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_jobs_engineer_completed", "engineer_jobs", ["engineer_id", "completed_at"]
        )
        op.create_index(
            "ix_jobs_engineer_payment", "engineer_jobs", ["engineer_id", "payment_status"]
        )
        op.create_index(
            "ix_jobs_engineer_service_type",
            "engineer_jobs",
            ["engineer_id", "service_type"],
        )


def downgrade() -> None:
    if _has_table("engineer_jobs"):
        op.drop_table("engineer_jobs")
    if _has_table("engineer_certifications"):
        op.drop_table("engineer_certifications")
    if _has_table("engineer_booking_requests"):
        op.drop_table("engineer_booking_requests")