"""VASS (Vehicle Assessment Safety System) rules for Australian vehicle standards."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


if TYPE_CHECKING:
    from app.models.vehicle import Vehicle


class VehicleClass(str, enum.Enum):
    """Australian vehicle classes per ADR definitions."""
    PASS_CAR = "PASS_CAR"          # Passenger car (MA)
    FORWARD_CONTROL = "FORWARD_CONTROL"  # Forward control passenger vehicle (MB)
    OFF_ROAD_PASS = "OFF_ROAD_PASS"      # Off-road passenger vehicle (MC)
    LIGHT_TRUCK = "LIGHT_TRUCK"          # Light truck / goods vehicle (NA)
    MEDIUM_TRUCK = "MEDIUM_TRUCK"        # Medium truck (NB)
    HEAVY_TRUCK = "HEAVY_TRUCK"          # Heavy truck (NC)
    MOTORCYCLE = "MOTORCYCLE"            # Motorcycle (LA/LB/LC/LD)
    HEAVY_BUS = "HEAVY_BUS"              # Heavy bus (MD)


class StandardType(str, enum.Enum):
    """Type of Australian standard/reference."""
    ADR = "ADR"
    VSI = "VSI"
    VSB6 = "VSB6"


class ModificationCategory(str, enum.Enum):
    """VASS modification categories mapped to VSB6 chapters."""
    LIGHTING = "LIGHTING"                    # VSB6 Chapter A
    BRAKING = "BRAKING"                      # VSB6 Chapter B
    SUSPENSION = "SUSPENSION"                # VSB6 Chapter C
    ENGINE = "ENGINE"                        # VSB6 Chapter D
    BODY = "BODY"                            # VSB6 Chapter E
    IDENTIFICATION = "IDENTIFICATION"        # VSB6 Chapter F
    OTHER = "OTHER"                          # VSB6 Chapter G


class ComplianceStatus(str, enum.Enum):
    """Compliance check result."""
    PASS = "PASS"
    FAIL = "FAIL"
    CONDITIONAL = "CONDITIONAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class VASRule(Base):
    """VASS rule mapping modifications to Australian standards."""
    
    __tablename__ = "vass_rules"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Modification identification
    mod_category: Mapped[ModificationCategory] = mapped_column(
        SQLEnum(ModificationCategory), nullable=False, index=True
    )
    mod_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    mod_description: Mapped[str | None] = mapped_column(Text)
    
    # Vehicle class this rule applies to
    vehicle_class: Mapped[VehicleClass] = mapped_column(
        SQLEnum(VehicleClass), nullable=False, index=True
    )
    
    # Standard reference
    standard_type: Mapped[StandardType] = mapped_column(
        SQLEnum(StandardType), nullable=False, index=True
    )
    standard_ref: Mapped[str] = mapped_column(String(40), nullable=False)  # e.g., "ADR 42/04", "VSB6 C.2.3"
    standard_section: Mapped[str | None] = mapped_column(String(80))       # Specific clause/section
    standard_title: Mapped[str | None] = mapped_column(String(200))
    
    # Compliance criteria
    default_status: Mapped[ComplianceStatus] = mapped_column(
        SQLEnum(ComplianceStatus), nullable=False, default=ComplianceStatus.CONDITIONAL
    )
    conditions: Mapped[str | None] = mapped_column(Text)  # JSON or text conditions for PASS
    notes: Mapped[str | None] = mapped_column(Text)
    
    # Metadata
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class VASCheck(Base):
    """VASS compliance check result for a vehicle/modification combination."""
    
    __tablename__ = "vass_checks"
    
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    vehicle_id: Mapped[str] = mapped_column(String(36), ForeignKey("vehicles.id"), index=True)
    modification_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("modifications.id"), index=True, nullable=True)
    
    # The rule that was applied
    rule_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("vass_rules.id"), nullable=True)
    
    # Input parameters
    mod_category: Mapped[str] = mapped_column(String(60), nullable=False)
    mod_name: Mapped[str] = mapped_column(String(120), nullable=False)
    vehicle_class: Mapped[str] = mapped_column(String(30), nullable=False)
    
    # Result
    status: Mapped[ComplianceStatus] = mapped_column(SQLEnum(ComplianceStatus), nullable=False)
    applied_standards: Mapped[str | None] = mapped_column(Text)  # JSON list of standard refs
    conditions_met: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    vehicle: Mapped["Vehicle"] = relationship("Vehicle")
    rule: Mapped["VASRule"] = relationship("VASRule")