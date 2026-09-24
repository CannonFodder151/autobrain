"""VASS (Vehicle Approval & Safety System) compliance models."""

import uuid
from datetime import date, datetime
from enum import Enum as PyEnum

from sqlalchemy import Date, DateTime, Enum, Float, ForeignKey, String, Text, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Jurisdiction(str, PyEnum):
    """Australian state/territory jurisdictions for VASS compliance."""
    VIC = "VIC"
    NSW = "NSW"
    QLD = "QLD"
    SA = "SA"
    WA = "WA"
    TAS = "TAS"
    ACT = "ACT"
    NT = "NT"


class ComplianceStatus(str, PyEnum):
    """Per-modification compliance outcome."""
    PASS = "pass"
    FAIL = "fail"
    CONDITIONAL = "conditional"
    PENDING = "pending"
    NOT_APPLICABLE = "na"


class PrecheckStatus(str, PyEnum):
    """Pre-check wizard completion state."""
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class EngineerType(str, PyEnum):
    """VASS engineer categories."""
    SIGNATORY = "signatory"
    INSPECTOR = "inspector"
    CONSULTANT = "consultant"


class VassPrecheck(Base):
    """Pre-check wizard session for a vehicle."""
    __tablename__ = "vass_prechecks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    jurisdiction: Mapped[Jurisdiction] = mapped_column(Enum(Jurisdiction, native_enum=False), default=Jurisdiction.VIC)
    status: Mapped[PrecheckStatus] = mapped_column(Enum(PrecheckStatus, native_enum=False), default=PrecheckStatus.DRAFT)
    vin: Mapped[str | None] = mapped_column(String(17))
    make: Mapped[str | None] = mapped_column(String(120))
    model: Mapped[str | None] = mapped_column(String(120))
    year: Mapped[int | None] = mapped_column()
    body_type: Mapped[str | None] = mapped_column(String(60))
    engine: Mapped[str | None] = mapped_column(String(120))
    transmission: Mapped[str | None] = mapped_column(String(60))
    modifications_json: Mapped[dict | None] = mapped_column(Text)  # JSON: list of mod selections
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_vass_precheck_vehicle_status", "vehicle_id", "status"),
    )


class ComplianceResult(Base):
    """Individual modification compliance outcome."""
    __tablename__ = "vass_compliance_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    precheck_id: Mapped[str] = mapped_column(String(36), ForeignKey("vass_prechecks.id"), index=True)
    modification_name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(60))
    status: Mapped[ComplianceStatus] = mapped_column(Enum(ComplianceStatus, native_enum=False), default=ComplianceStatus.PENDING)
    adr_references: Mapped[list | None] = mapped_column(Text)  # JSON list of ADR codes
    vsb_references: Mapped[list | None] = mapped_column(Text)  # JSON list of VSB codes
    vsb6_references: Mapped[list | None] = mapped_column(Text)  # JSON list of VSB6 codes
    notes: Mapped[str | None] = mapped_column(Text)
    conditional_details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Engineer(Base):
    """VASS engineer registry."""
    __tablename__ = "vass_engineers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    jurisdiction: Mapped[Jurisdiction] = mapped_column(Enum(Jurisdiction, native_enum=False), index=True)
    engineer_type: Mapped[EngineerType] = mapped_column(Enum(EngineerType, native_enum=False), default=EngineerType.SIGNATORY)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    business_name: Mapped[str | None] = mapped_column(String(200))
    abn: Mapped[str | None] = mapped_column(String(11))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(30))
    address: Mapped[str | None] = mapped_column(Text)
    suburb: Mapped[str | None] = mapped_column(String(120))
    postcode: Mapped[str | None] = mapped_column(String(10))
    specialisations: Mapped[list | None] = mapped_column(Text)  # JSON list
    license_number: Mapped[str | None] = mapped_column(String(50))
    license_expiry: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(default=True)
    rating: Mapped[float | None] = mapped_column(Float)
    review_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_vass_engineer_jurisdiction_type", "jurisdiction", "engineer_type"),
    )


class EngineerRequest(Base):
    """User request to engage an engineer."""
    __tablename__ = "vass_engineer_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    engineer_id: Mapped[str] = mapped_column(String(36), ForeignKey("vass_engineers.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    vehicle_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("vehicles.id"))
    precheck_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("vass_prechecks.id"))
    message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending/accepted/declined/completed
    quoted_amount: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ImportPathway(Base):
    """Import compliance pathway for a VIN."""
    __tablename__ = "vass_import_pathways"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    vin: Mapped[str] = mapped_column(String(17), index=True)
    jurisdiction: Mapped[Jurisdiction] = mapped_column(Enum(Jurisdiction, native_enum=False))
    vehicle_make: Mapped[str | None] = mapped_column(String(120))
    vehicle_model: Mapped[str | None] = mapped_column(String(120))
    vehicle_year: Mapped[int | None] = mapped_column()
    pathway_type: Mapped[str] = mapped_column(String(50))  # personal_import, sevs, raws, etc.
    eligibility: Mapped[str] = mapped_column(Text)  # eligible/conditional/not_eligible
    requirements_json: Mapped[dict | None] = mapped_column(Text)  # JSON: document checklist, steps
    adr_requirements: Mapped[list | None] = mapped_column(Text)  # JSON list
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_vass_import_pathway_vin_jurisdiction", "vin", "jurisdiction", unique=True),
    )


class CompliancePack(Base):
    """Generated compliance PDF pack."""
    __tablename__ = "vass_compliance_packs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    precheck_id: Mapped[str] = mapped_column(String(36), ForeignKey("vass_prechecks.id"), index=True)
    minio_key: Mapped[str] = mapped_column(String(500))  # MinIO object key
    filename: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column()
    overall_score: Mapped[float | None] = mapped_column(Float)
    total_mods: Mapped[int] = mapped_column(default=0)
    passed_mods: Mapped[int] = mapped_column(default=0)
    failed_mods: Mapped[int] = mapped_column(default=0)
    conditional_mods: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())