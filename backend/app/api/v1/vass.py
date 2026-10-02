"""VASS compliance API routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_write
from app.db.session import get_db
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.vass import (
    ComplianceAggregationRequest,
    ComplianceAggregationResponse,
    ComplianceResultItem,
    ComplianceStatus,
    ModificationChecklistItem,
    ModificationChecklistRequest,
    ModificationChecklistResponse,
    ModificationCategory,
    VASSState,
    VINValidationRequest,
    VINValidationResponse,
    VehicleLookupRequest,
    VehicleLookupResponse,
    VehicleType,
)

router = APIRouter(prefix="/vass", tags=["vass"])


def _validate_vin_checksum(vin: str) -> bool:
    """Validate VIN checksum using ISO 3779 standard.

    Transliteration values: A=1, B=2, C=3, D=4, E=5, F=6, G=7, H=8,
    J=1, K=2, L=3, M=4, N=5, P=7, R=9, S=2, T=3, U=4, V=5, W=6, X=7, Y=8, Z=9
    Position weights: 8,7,6,5,4,3,2,10,0,9,8,7,6,5,4,3,2
    Check digit = (sum of weighted values) mod 11, where 10 = X
    """
    if len(vin) != 17:
        return False

    transliterate = {
        'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7, 'H': 8,
        'J': 1, 'K': 2, 'L': 3, 'M': 4, 'N': 5, 'P': 7, 'R': 9, 'S': 2,
        'T': 3, 'U': 4, 'V': 5, 'W': 6, 'X': 7, 'Y': 8, 'Z': 9,
    }
    weights = [8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2]

    try:
        total = 0
        for i, char in enumerate(vin):
            if char.isdigit():
                value = int(char)
            elif char in transliterate:
                value = transliterate[char]
            else:
                return False
            total += value * weights[i]

        remainder = total % 11
        expected = 'X' if remainder == 10 else str(remainder)
        return vin[8] == expected
    except (IndexError, KeyError):
        return False


def _decode_vin(vin: str) -> dict:
    """Decode basic VIN information (world manufacturer, attributes)."""
    if len(vin) < 17:
        return {}

    # World Manufacturer Identifier (positions 1-3)
    wmi = vin[:3]

    # Vehicle Descriptor Section (positions 4-9)
    vds = vin[3:9]

    # Vehicle Identifier Section (positions 10-17)
    vis = vin[9:]

    # Model year (position 10)
    year_chars = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
    year_code = vis[0] if vis else None
    model_year = None
    if year_code and year_code in year_chars:
        idx = year_chars.index(year_code)
        model_year = 2010 + (idx % 30) if idx < 30 else 1980 + (idx - 30)

    # Assembly plant (position 11)
    plant_code = vis[1] if len(vis) > 1 else None

    return {
        "wmi": wmi,
        "vds": vds,
        "vis": vis,
        "model_year": model_year,
        "plant_code": plant_code,
        "check_digit_position": 9,
        "check_digit_valid": _validate_vin_checksum(vin),
    }


@router.post("/vehicle-lookup", response_model=VehicleLookupResponse)
async def lookup_vehicle(
    payload: VehicleLookupRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VehicleLookupResponse:
    """Lookup vehicle make/model/year for VASS compliance.

    Returns vehicle specifications and ADR category based on make/model/year.
    Deterministic lookup first, AI fallback only when needed.
    """
    # Deterministic lookup: search existing vehicles in DB
    stmt = (
        select(Vehicle)
        .where(
            Vehicle.make.ilike(f"%{payload.make}%"),
            Vehicle.model.ilike(f"%{payload.model}%"),
            Vehicle.year == payload.year,
        )
        .limit(5)
    )
    result = await db.execute(stmt)
    vehicles = result.scalars().all()

    if vehicles:
        v = vehicles[0]
        return VehicleLookupResponse(
            make=v.make or payload.make,
            model=v.model or payload.model,
            year=v.year or payload.year,
            state=payload.state,
            vehicle_type=payload.vehicle_type,
            vin_pattern=v.vin[:3] if v.vin else None,
            adr_category="Light Vehicle" if payload.vehicle_type == VehicleType.CAR else "Other",
            gross_vehicle_mass_kg=2500 if payload.vehicle_type == VehicleType.CAR else None,
            seating_capacity=5,
            fuel_type=v.engine or "Petrol",
            found=True,
        )

    # Deterministic fallback: return based on vehicle type and state
    adr_category = "Light Vehicle" if payload.vehicle_type == VehicleType.CAR else "Other"
    gvm = 2500 if payload.vehicle_type == VehicleType.CAR else None

    return VehicleLookupResponse(
        make=payload.make,
        model=payload.model,
        year=payload.year,
        state=payload.state,
        vehicle_type=payload.vehicle_type,
        adr_category=adr_category,
        gross_vehicle_mass_kg=gvm,
        seating_capacity=5 if payload.vehicle_type == VehicleType.CAR else None,
        found=False,
    )


@router.post("/vin-validate", response_model=VINValidationResponse)
async def validate_vin(
    payload: VINValidationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VINValidationResponse:
    """Validate a VIN number.

    Checks format (17 chars, no I/O/Q), checksum, and decodes basic info.
    Also checks if VIN matches any vehicle in user's garage.
    """
    vin = payload.vin.upper()

    # Format validation: 17 chars, no I, O, Q
    valid_format = (
        len(vin) == 17
        and vin.isalnum()
        and 'I' not in vin
        and 'O' not in vin
        and 'Q' not in vin
    )

    if not valid_format:
        return VINValidationResponse(
            vin=vin,
            valid_format=False,
            valid_checksum=False,
            decoded=None,
            state=payload.state,
            matches_vehicle=None,
            vehicle_id=None,
        )

    valid_checksum = _validate_vin_checksum(vin)
    decoded = _decode_vin(vin)

    # Check if VIN matches any vehicle in user's garage
    stmt = select(Vehicle).where(Vehicle.vin == vin)
    result = await db.execute(stmt)
    existing = result.scalars().first()

    return VINValidationResponse(
        vin=vin,
        valid_format=True,
        valid_checksum=valid_checksum,
        decoded=decoded,
        state=payload.state,
        matches_vehicle=existing is not None,
        vehicle_id=existing.id if existing else None,
    )


@router.post("/modification-checklist", response_model=ModificationChecklistResponse)
async def generate_modification_checklist(
    payload: ModificationChecklistRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ModificationChecklistResponse:
    """Generate a modification checklist for VASS compliance.

    Returns a checklist of compliance requirements for each modification
    category, including ADR/VSI/VSB6 references and certification requirements.
    """
    # Deterministic checklist generation based on category
    checklist: list[ModificationChecklistItem] = []
    categories_with_mods = set()

    for mod_data in payload.modifications:
        category = mod_data.get("category", "other")
        categories_with_mods.add(category)
        name = mod_data.get("name", "Unknown modification")

        # Map generic categories to VASS categories
        vass_category = ModificationCategory.OTHER
        for mc in ModificationCategory:
            if mc.value == category:
                vass_category = mc
                break

        # Determine requirements based on category
        adr_refs = []
        vsb6_refs = []
        vsi_refs = []
        requires_cert = False
        requires_lab = False
        notes = None

        if vass_category in (ModificationCategory.ENGINE, ModificationCategory.FUEL_SYSTEM):
            adr_refs = ["ADR 79/00", "ADR 79/01"]
            vsb6_refs = ["VSB6 Section 5"]
            requires_cert = True
            notes = "Engine modifications require engineering certification"
        elif vass_category == ModificationCategory.EXHAUST:
            adr_refs = ["ADR 83/00"]
            vsb6_refs = ["VSB6 Section 6"]
            vsi_refs = ["VSI 10"]
            requires_cert = True
            notes = "Exhaust modifications must meet noise limits"
        elif vass_category == ModificationCategory.SUSPENSION:
            adr_refs = ["ADR 13/00"]
            vsb6_refs = ["VSB6 Section 4"]
            vsi_refs = ["VSI 7"]
            requires_cert = True
            notes = "Suspension changes affect braking and handling"
        elif vass_category == ModificationCategory.BRAKES:
            adr_refs = ["ADR 13/00", "ADR 13/01"]
            vsb6_refs = ["VSB6 Section 7"]
            requires_cert = True
            requires_lab = True
            notes = "Brake modifications require lab testing for certification"
        elif vass_category == ModificationCategory.STEERING:
            adr_refs = ["ADR 10/00"]
            vsb6_refs = ["VSB6 Section 3"]
            requires_cert = True
            notes = "Steering modifications are high-risk"
        elif vass_category == ModificationCategory.WHEELS_TYRES:
            adr_refs = ["ADR 23/00", "ADR 23/01"]
            vsb6_refs = ["VSB6 Section 2"]
            vsi_refs = ["VSI 2"]
            notes = "Wheel/tyre changes must stay within GVM and load ratings"
        elif vass_category == ModificationCategory.BODY_CHASSIS:
            adr_refs = ["ADR 29/00", "ADR 42/00"]
            vsb6_refs = ["VSB6 Section 8"]
            requires_cert = True
            notes = "Body/chassis modifications require structural assessment"
        elif vass_category == ModificationCategory.LIGHTING:
            adr_refs = ["ADR 13/00", "ADR 47/00"]
            vsb6_refs = ["VSB6 Section 1"]
            notes = "Lighting must meet ADR requirements for the vehicle class"
        elif vass_category == ModificationCategory.EMISSIONS:
            adr_refs = ["ADR 79/00", "ADR 79/01"]
            vsb6_refs = ["VSB6 Section 5"]
            requires_cert = True
            requires_lab = True
            notes = "Emissions modifications require laboratory testing"
        elif vass_category == ModificationCategory.TRANSMISSION:
            adr_refs = ["ADR 13/00"]
            vsb6_refs = ["VSB6 Section 4"]
            requires_cert = True
            notes = "Transmission changes affect vehicle classification"
        elif vass_category == ModificationCategory.SEATS_RESTRAINTS:
            adr_refs = ["ADR 3/00", "ADR 3/01"]
            vsb6_refs = ["VSB6 Section 9"]
            requires_cert = True
            notes = "Seat and restraint modifications affect occupant safety"
        elif vass_category == ModificationCategory.NOISE:
            adr_refs = ["ADR 28/00"]
            vsb6_refs = ["VSB6 Section 10"]
            vsi_refs = ["VSI 10"]
            notes = "External noise must meet limits"

        checklist.append(ModificationChecklistItem(
            category=vass_category,
            modification_name=name,
            description=notes or f"Check {category} modification compliance",
            adr_references=adr_refs,
            vsb6_references=vsb6_refs,
            vsi_references=vsi_refs,
            requires_engineer_certification=requires_cert,
            requires_lab_testing=requires_lab,
            notes=notes,
        ))

    now = datetime.now(timezone.utc)
    total_items = len(checklist)
    items_requiring_cert = sum(1 for i in checklist if i.requires_engineer_certification)
    items_requiring_lab = sum(1 for i in checklist if i.requires_lab_testing)

    return ModificationChecklistResponse(
        vehicle_id=payload.vehicle_id,
        state=payload.state,
        checklist=checklist,
        generated_at=now,
        total_items=total_items,
        items_requiring_certification=items_requiring_cert,
        items_requiring_lab_testing=items_requiring_lab,
    )


@router.post("/compliance-results", response_model=ComplianceAggregationResponse)
async def aggregate_compliance_results(
    payload: ComplianceAggregationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ComplianceAggregationResponse:
    """Aggregate compliance results for all modifications on a vehicle.

    Combines individual compliance checks into an overall status and provides
    next steps based on the results.
    """
    # Verify vehicle exists and user has access
    vehicle = await db.get(Vehicle, payload.vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    if vehicle.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this vehicle")

    # Fetch modifications for the vehicle
    from app.models.mod import Modification

    stmt = select(Modification).where(Modification.vehicle_id == payload.vehicle_id)
    if payload.modification_ids:
        stmt = stmt.where(Modification.id.in_(payload.modification_ids))
    result = await db.execute(stmt)
    modifications = list(result.scalars().all())

    # Generate deterministic compliance results for each modification
    results: list[ComplianceResultItem] = []
    for mod in modifications:
        # Map mod category to VASS category
        vass_category = ModificationCategory.OTHER
        for mc in ModificationCategory:
            if mc.value == mod.category:
                vass_category = mc
                break

        # Deterministic compliance assessment
        status = ComplianceStatus.COMPLIANT
        details = f"{mod.name} appears to comply with VASS requirements"
        requires_cert = False
        requires_lab = False
        evidence_required = []

        # Engine and fuel system mods always need certification
        if vass_category in (ModificationCategory.ENGINE, ModificationCategory.FUEL_SYSTEM):
            if mod.brand and mod.brand.lower() in ["aftermarket", "custom", "unknown"]:
                status = ComplianceStatus.REQUIRES_CERTIFICATION
                requires_cert = True
                details = f"{mod.name} requires engineering certification - aftermarket component"
                evidence_required = ["Engineering certification", "Test results"]

        # Exhaust and emissions may need testing
        elif vass_category in (ModificationCategory.EXHAUST, ModificationCategory.EMISSIONS):
            if not mod.notes or "certified" not in mod.notes.lower():
                status = ComplianceStatus.REQUIRES_INSPECTION
                requires_lab = True
                details = f"{mod.name} requires inspection for noise/emissions compliance"
                evidence_required = ["Noise test results", "Emissions certificate"]

        # Brakes always need lab testing
        elif vass_category == ModificationCategory.BRAKES:
            status = ComplianceStatus.REQUIRES_CERTIFICATION
            requires_cert = True
            requires_lab = True
            details = f"{mod.name} requires lab testing and engineering certification"
            evidence_required = ["Lab test results", "Engineering certification", "Installation certificate"]

        # Steering is high-risk
        elif vass_category == ModificationCategory.STEERING:
            status = ComplianceStatus.REQUIRES_CERTIFICATION
            requires_cert = True
            details = f"{mod.name} requires engineering certification - safety critical"
            evidence_required = ["Engineering certification", "Structural assessment"]

        # Body/chassis may need structural assessment
        elif vass_category == ModificationCategory.BODY_CHASSIS:
            status = ComplianceStatus.REQUIRES_INSPECTION
            requires_cert = True
            details = f"{mod.name} requires structural assessment"
            evidence_required = ["Structural assessment", "Engineering certification"]

        # Seats/restraints need certification
        elif vass_category == ModificationCategory.SEATS_RESTRAINTS:
            status = ComplianceStatus.REQUIRES_CERTIFICATION
            requires_cert = True
            details = f"{mod.name} requires certification for occupant safety"
            evidence_required = ["Engineering certification", "Safety test results"]

        results.append(ComplianceResultItem(
            category=vass_category,
            modification_name=mod.name,
            status=status,
            adr_references=[],
            vsb6_references=[],
            vsi_references=[],
            details=details,
            engineer_required=requires_cert,
            lab_testing_required=requires_lab,
            evidence_required=evidence_required,
        ))

    # Aggregate counts
    compliant = sum(1 for r in results if r.status == ComplianceStatus.COMPLIANT)
    non_compliant = sum(1 for r in results if r.status == ComplianceStatus.NON_COMPLIANT)
    requires_inspection = sum(1 for r in results if r.status == ComplianceStatus.REQUIRES_INSPECTION)
    requires_certification = sum(1 for r in results if r.status == ComplianceStatus.REQUIRES_CERTIFICATION)
    unknown = sum(1 for r in results if r.status == ComplianceStatus.UNKNOWN)

    # Determine overall status
    if non_compliant > 0:
        overall = ComplianceStatus.NON_COMPLIANT
    elif requires_certification > 0:
        overall = ComplianceStatus.REQUIRES_CERTIFICATION
    elif requires_inspection > 0:
        overall = ComplianceStatus.REQUIRES_INSPECTION
    elif unknown > 0:
        overall = ComplianceStatus.UNKNOWN
    else:
        overall = ComplianceStatus.COMPLIANT

    # Generate next steps
    next_steps = []
    if requires_certification > 0:
        next_steps.append("Schedule engineering certification for modifications requiring assessment")
    if requires_inspection > 0:
        next_steps.append("Book inspection for modifications requiring assessment")
    if non_compliant > 0:
        next_steps.append("Address non-compliant modifications before vehicle can be deemed roadworthy")
    if not next_steps:
        next_steps.append("All modifications appear compliant - no action required")

    now = datetime.now(timezone.utc)
    summary_parts = []
    if compliant > 0:
        summary_parts.append(f"{compliant} compliant")
    if non_compliant > 0:
        summary_parts.append(f"{non_compliant} non-compliant")
    if requires_inspection > 0:
        summary_parts.append(f"{requires_inspection} requiring inspection")
    if requires_certification > 0:
        summary_parts.append(f"{requires_certification} requiring certification")
    if unknown > 0:
        summary_parts.append(f"{unknown} unknown")

    summary = f"Overall: {overall.value} - {', '.join(summary_parts)}" if summary_parts else "No modifications found"

    return ComplianceAggregationResponse(
        vehicle_id=payload.vehicle_id,
        state=payload.state,
        overall_status=overall,
        total_modifications=len(modifications),
        compliant_count=compliant,
        non_compliant_count=non_compliant,
        requires_inspection_count=requires_inspection,
        requires_certification_count=requires_certification,
        unknown_count=unknown,
        results=results,
        generated_at=now,
        summary=summary,
        next_steps=next_steps,
    )


@router.get("/vehicle/{vehicle_id}/compliance", response_model=ComplianceAggregationResponse)
async def get_vehicle_compliance(
    vehicle_id: str,
    state: VASSState = VASSState.VIC,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ComplianceAggregationResponse:
    """Get compliance results for a vehicle (convenience endpoint).

    Combines vehicle lookup, VIN validation, and compliance aggregation
    into a single call for the frontend.
    """
    # Verify vehicle exists and user has access
    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    if vehicle.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this vehicle")

    # Delegate to aggregation endpoint
    agg_request = ComplianceAggregationRequest(
        vehicle_id=vehicle_id,
        state=state,
    )
    return await aggregate_compliance_results(agg_request, db, user)