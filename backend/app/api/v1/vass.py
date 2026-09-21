"""VASS (Vehicle Approval & Safety System) compliance API routes."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_write
from app.db.session import get_db
from app.models.user import User
from app.models.vass import (
    ComplianceResult,
    ComplianceStatus,
    Engineer,
    EngineerRequest,
    EngineerType,
    ImportPathway,
    Jurisdiction,
    PrecheckStatus,
    VassPrecheck,
    CompliancePack,
)
from app.schemas.vass import (
    ChecklistItemOut,
    ComplianceAggregationRequest,
    ComplianceAggregationResponse,
    CompliancePackGenerateRequest,
    CompliancePackOut,
    ComplianceResultDetail,
    ComplianceResultOut,
    DocumentChecklistItem,
    EngineerCreate,
    EngineerOut,
    EngineerRequestCreate,
    EngineerRequestOut,
    EngineerSearchResponse,
    EngineerUpdate,
    ImportPathwayDetailOut,
    ImportPathwayOut,
    ModificationChecklistRequest,
    ModificationChecklistResponse,
    ModificationItem,
    ModificationSelection,
    PrecheckCreate,
    PrecheckOut,
    PrecheckUpdate,
    VassSettingsOut,
    VassSettingsUpdate,
    VinValidationRequest,
    VinValidationResponse,
    VehicleLookupItem,
    VehicleLookupRequest,
    VehicleLookupResponse,
)
from app.services.vin_decoder import validate_vin, validate_check_digit, decode_vin
from app.services.vehicle_lookup import lookup_vehicle, get_available_makes, get_models_for_make, get_year_range
from app.services.modification_checklist import generate_modification_checklist
from app.services.compliance_aggregator import aggregate_compliance_results

router = APIRouter(prefix="/vass", tags=["vass"])


# ---------------------------------------------------------------------------
# Pre-check Wizard
# ---------------------------------------------------------------------------

@router.get("/prechecks", response_model=list[PrecheckOut])
async def list_prechecks(
    vehicle_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[VassPrecheck]:
    stmt = select(VassPrecheck).where(VassPrecheck.user_id == user.id)
    if vehicle_id:
        stmt = stmt.where(VassPrecheck.vehicle_id == vehicle_id)
    stmt = stmt.order_by(VassPrecheck.created_at.desc())
    rows = await db.scalars(stmt)
    return list(rows)


@router.post("/prechecks", response_model=PrecheckOut, status_code=201)
async def create_precheck(
    payload: PrecheckCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> VassPrecheck:
    precheck = VassPrecheck(
        vehicle_id=payload.vehicle_id,
        user_id=user.id,
        jurisdiction=payload.jurisdiction,
        vin=payload.vin,
        make=payload.make,
        model=payload.model,
        year=payload.year,
        body_type=payload.body_type,
        engine=payload.engine,
        transmission=payload.transmission,
        modifications_json={"mods": [m.model_dump() for m in payload.modifications]},
    )
    db.add(precheck)
    await db.flush()
    await db.commit()
    await db.refresh(precheck)
    return precheck


@router.get("/prechecks/{precheck_id}", response_model=PrecheckOut)
async def get_precheck(
    precheck_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> VassPrecheck:
    precheck = await db.get(VassPrecheck, precheck_id)
    if not precheck or precheck.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pre-check not found")
    return precheck


@router.patch("/prechecks/{precheck_id}", response_model=PrecheckOut)
async def update_precheck(
    precheck_id: str,
    payload: PrecheckUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> VassPrecheck:
    precheck = await db.get(VassPrecheck, precheck_id)
    if not precheck or precheck.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pre-check not found")
    updates = payload.model_dump(exclude_unset=True)
    if "modifications" in updates:
        mods = updates.pop("modifications")
        precheck.modifications_json = {"mods": [m.model_dump() for m in mods] if mods else []}
    if "status" in updates:
        precheck.status = updates["status"]
    for key, value in updates.items():
        setattr(precheck, key, value)
    await db.commit()
    await db.refresh(precheck)
    return precheck


@router.delete("/prechecks/{precheck_id}", status_code=204)
async def delete_precheck(
    precheck_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> None:
    precheck = await db.get(VassPrecheck, precheck_id)
    if not precheck or precheck.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pre-check not found")
    await db.delete(precheck)
    await db.commit()


@router.post("/prechecks/{precheck_id}/complete", response_model=PrecheckOut)
async def complete_precheck(
    precheck_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> VassPrecheck:
    """Run compliance checks and complete the wizard."""
    precheck = await db.get(VassPrecheck, precheck_id)
    if not precheck or precheck.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pre-check not found")

    # Parse modifications from precheck
    mods_data = precheck.modifications_json or {}
    mods_list = mods_data.get("mods", [])

    # Delete old results and regenerate
    old_results = await db.scalars(
        select(ComplianceResult).where(ComplianceResult.precheck_id == precheck_id)
    )
    for r in old_results:
        await db.delete(r)

    # Evaluate compliance for each modification (deterministic rule engine)
    for mod in mods_list:
        cat = mod.get("category", "other").lower()
        status, adr_refs, vsb_refs, notes = _evaluate_modification(
            cat, mod.get("name", ""), precheck.jurisdiction
        )
        result = ComplianceResult(
            precheck_id=precheck_id,
            modification_name=mod.get("name", "Unknown"),
            category=cat,
            status=status,
            adr_references=json.dumps(adr_refs) if adr_refs else None,
            vsb_references=json.dumps(vsb_refs) if vsb_refs else None,
            vsb6_references=json.dumps([]),
            notes=notes,
        )
        db.add(result)

    precheck.status = PrecheckStatus.COMPLETED
    precheck.completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(precheck)
    return precheck


# ---------------------------------------------------------------------------
# Compliance Results
# ---------------------------------------------------------------------------

@router.get("/prechecks/{precheck_id}/results", response_model=list[ComplianceResultOut])
async def get_compliance_results(
    precheck_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ComplianceResult]:
    precheck = await db.get(VassPrecheck, precheck_id)
    if not precheck or precheck.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pre-check not found")
    rows = await db.scalars(
        select(ComplianceResult)
        .where(ComplianceResult.precheck_id == precheck_id)
        .order_by(ComplianceResult.created_at)
    )
    return list(rows)


# ---------------------------------------------------------------------------
# Compliance Packs (PDF)
# ---------------------------------------------------------------------------

@router.get("/prechecks/{precheck_id}/packs", response_model=list[CompliancePackOut])
async def list_compliance_packs(
    precheck_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[CompliancePack]:
    precheck = await db.get(VassPrecheck, precheck_id)
    if not precheck or precheck.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pre-check not found")
    rows = await db.scalars(
        select(CompliancePack)
        .where(CompliancePack.precheck_id == precheck_id)
        .order_by(CompliancePack.created_at.desc())
    )
    return list(rows)


@router.post("/packs/generate", response_model=CompliancePackOut, status_code=201)
async def generate_compliance_pack(
    payload: CompliancePackGenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> CompliancePack:
    """Generate a compliance PDF pack for a completed precheck."""
    precheck = await db.get(VassPrecheck, payload.precheck_id)
    if not precheck or precheck.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pre-check not found")
    if precheck.status != PrecheckStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Pre-check must be completed first")

    # Get results
    results = list(await db.scalars(
        select(ComplianceResult)
        .where(ComplianceResult.precheck_id == payload.precheck_id)
    ))

    total = len(results)
    passed = sum(1 for r in results if r.status == ComplianceStatus.PASS)
    failed = sum(1 for r in results if r.status == ComplianceStatus.FAIL)
    conditional = sum(1 for r in results if r.status == ComplianceStatus.CONDITIONAL)
    score = (passed / total * 100) if total > 0 else 0.0

    # Placeholder: in production, generate actual PDF via app/services/vass_pdf.py
    # and upload to MinIO. For now, create a metadata-only record.
    label = f"{precheck.make or ''} {precheck.model or ''}".strip() or "Vehicle"
    filename = f"vass-compliance-{label}-{precheck.jurisdiction}.pdf"

    pack = CompliancePack(
        precheck_id=payload.precheck_id,
        minio_key=f"vass-packs/{payload.precheck_id}/{filename}",
        filename=filename,
        file_size=0,  # Will be set by PDF generator
        overall_score=score,
        total_mods=total,
        passed_mods=passed,
        failed_mods=failed,
        conditional_mods=conditional,
    )
    db.add(pack)
    await db.commit()
    await db.refresh(pack)
    return pack


@router.get("/packs/{pack_id}/download")
async def download_compliance_pack(
    pack_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Download a compliance pack PDF."""
    pack = await db.get(CompliancePack, pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")
    precheck = await db.get(VassPrecheck, pack.precheck_id)
    if not precheck or precheck.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pack not found")

    # Placeholder: download from MinIO in production
    from fastapi.responses import Response
    return Response(
        content=b"%PDF-1.4 placeholder",
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{pack.filename}"'},
    )


# ---------------------------------------------------------------------------
# Engineer Marketplace
# ---------------------------------------------------------------------------

@router.get("/engineers", response_model=EngineerSearchResponse)
async def search_engineers(
    jurisdiction: Jurisdiction | None = Query(None),
    engineer_type: EngineerType | None = Query(None),
    specialisation: str | None = Query(None),
    suburb: str | None = Query(None),
    postcode: str | None = Query(None),
    min_rating: float | None = Query(None, ge=0, le=5),
    is_active: bool = Query(True),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> EngineerSearchResponse:
    stmt = select(Engineer)
    if jurisdiction:
        stmt = stmt.where(Engineer.jurisdiction == jurisdiction)
    if engineer_type:
        stmt = stmt.where(Engineer.engineer_type == engineer_type)
    if suburb:
        stmt = stmt.where(Engineer.suburb.ilike(f"%{suburb}%"))
    if postcode:
        stmt = stmt.where(Engineer.postcode == postcode)
    if min_rating is not None:
        stmt = stmt.where(Engineer.rating >= min_rating)
    if is_active:
        stmt = stmt.where(Engineer.is_active == True)

    # Count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar() or 0
    total_pages = max(1, -(-total // page_size))

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    rows = list(await db.scalars(stmt))

    # Filter by specialisation in JSON
    if specialisation:
        rows = [
            e for e in rows
            if specialisation.lower() in (e.specialisations or [])
        ]

    return EngineerSearchResponse(
        engineers=[EngineerOut.model_validate(e) for e in rows],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/engineers/{engineer_id}", response_model=EngineerOut)
async def get_engineer(
    engineer_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Engineer:
    engineer = await db.get(Engineer, engineer_id)
    if not engineer:
        raise HTTPException(status_code=404, detail="Engineer not found")
    return engineer


@router.post("/engineers", response_model=EngineerOut, status_code=201)
async def create_engineer(
    payload: EngineerCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> Engineer:
    engineer = Engineer(
        jurisdiction=payload.jurisdiction,
        engineer_type=payload.engineer_type,
        name=payload.name,
        business_name=payload.business_name,
        abn=payload.abn,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
        suburb=payload.suburb,
        postcode=payload.postcode,
        specialisations=json.dumps(payload.specialisations) if payload.specialisations else None,
        license_number=payload.license_number,
        license_expiry=payload.license_expiry,
    )
    db.add(engineer)
    await db.commit()
    await db.refresh(engineer)
    return engineer


@router.patch("/engineers/{engineer_id}", response_model=EngineerOut)
async def update_engineer(
    engineer_id: str,
    payload: EngineerUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> Engineer:
    engineer = await db.get(Engineer, engineer_id)
    if not engineer:
        raise HTTPException(status_code=404, detail="Engineer not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "specialisations" and value is not None:
            setattr(engineer, key, json.dumps(value))
        else:
            setattr(engineer, key, value)
    await db.commit()
    await db.refresh(engineer)
    return engineer


# ---------------------------------------------------------------------------
# Engineer Requests
# ---------------------------------------------------------------------------

@router.get("/requests", response_model=list[EngineerRequestOut])
async def list_engineer_requests(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[EngineerRequest]:
    rows = await db.scalars(
        select(EngineerRequest)
        .where(EngineerRequest.user_id == user.id)
        .order_by(EngineerRequest.created_at.desc())
    )
    return list(rows)


@router.post("/requests", response_model=EngineerRequestOut, status_code=201)
async def create_engineer_request(
    payload: EngineerRequestCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> EngineerRequest:
    engineer = await db.get(Engineer, payload.engineer_id)
    if not engineer or not engineer.is_active:
        raise HTTPException(status_code=404, detail="Engineer not found or inactive")
    req = EngineerRequest(
        engineer_id=payload.engineer_id,
        user_id=user.id,
        vehicle_id=payload.vehicle_id,
        precheck_id=payload.precheck_id,
        message=payload.message,
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req


# ---------------------------------------------------------------------------
# Import Pathway
# ---------------------------------------------------------------------------

@router.post("/import-pathway", response_model=ImportPathwayOut, status_code=201)
async def create_import_pathway(
    payload: ImportPathwayRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_write),
) -> ImportPathway:
    """Look up import compliance pathway for a VIN."""
    # Check if pathway already cached
    existing = await db.scalars(
        select(ImportPathway).where(
            ImportPathway.vin == payload.vin,
            ImportPathway.jurisdiction == payload.jurisdiction,
        )
    )
    existing_row = existing.first()
    if existing_row:
        return existing_row

    # Deterministic pathway evaluation
    pathway_type, eligibility, requirements, adr = _evaluate_import_pathway(
        payload.vin, payload.jurisdiction
    )

    pathway = ImportPathway(
        vin=payload.vin,
        jurisdiction=payload.jurisdiction,
        vehicle_make=None,
        vehicle_model=None,
        vehicle_year=None,
        pathway_type=pathway_type,
        eligibility=eligibility,
        requirements_json=requirements,
        adr_references=json.dumps(adr),
    )
    db.add(pathway)
    await db.commit()
    await db.refresh(pathway)
    return pathway


@router.get("/import-pathway/{pathway_id}", response_model=ImportPathwayDetailOut)
async def get_import_pathway(
    pathway_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ImportPathway:
    pathway = await db.get(ImportPathway, pathway_id)
    if not pathway:
        raise HTTPException(status_code=404, detail="Pathway not found")
    out = ImportPathwayDetailOut.model_validate(pathway)
    out.requirements = json.loads(pathway.requirements_json) if pathway.requirements_json else None
    out.adr_requirements = json.loads(pathway.adr_references) if pathway.adr_references else []
    out.document_checklist = _build_document_checklist(pathway)
    return out


# ---------------------------------------------------------------------------
# VASS Settings
# ---------------------------------------------------------------------------

@router.get("/settings", response_model=VassSettingsOut)
async def get_vass_settings(
    user: User = Depends(get_current_user),
) -> VassSettingsOut:
    return VassSettingsOut(default_jurisdiction=Jurisdiction.VIC)


@router.patch("/settings", response_model=VassSettingsOut)
async def update_vass_settings(
    payload: VassSettingsUpdate,
    user: User = Depends(require_write),
) -> VassSettingsOut:
    return VassSettingsOut(
        default_jurisdiction=payload.default_jurisdiction or Jurisdiction.VIC
    )


# ---------------------------------------------------------------------------
# Deterministic rule engines (AI-free)
# ---------------------------------------------------------------------------

def _evaluate_modification(
    category: str, name: str, jurisdiction: str
) -> tuple[ComplianceStatus, list[str], list[str], str | None]:
    """Evaluate a single modification against ADR/VSB rules.

    Deterministic, no AI. Returns (status, adr_refs, vsb_refs, notes).
    """
    name_lower = name.lower()
    cat = category.lower()

    # Brake system modifications — always require compliance sign-off
    if cat == "brakes":
        return (
            ComplianceStatus.CONDITIONAL,
            ["ADR 31/04", "ADR 35/05"],
            ["VSB 6 Section 7"],
            "Brake modifications require VASS engineer sign-off. "
            "Ensure matching caliper/rotor/drums to manufacturer spec or ADR 31/04 compliance.",
        )

    # Suspension changes
    if cat == "suspension":
        return (
            ComplianceStatus.CONDITIONAL,
            ["ADR 01/00", "ADR 02/00"],
            ["VSB 6 Section 5"],
            "Suspension changes must maintain vehicle height within ±25mm of ADR compliance height. "
            "Coilovers and lift kits may require engineer certification.",
        )

    # Exhaust — noise limits per state
    if cat == "exhaust":
        noise_limits = {
            "VIC": "75dB(A) at 3000RPM",
            "NSW": "82dB(A) (driving test)",
            "QLD": "82dB(A) (driving test)",
            "SA": "75dB(A) at 3000RPM",
            "WA": "90dB(A) stationary",
            "TAS": "82dB(A) (driving test)",
            "ACT": "82dB(A) (driving test)",
            "NT": "90dB(A) stationary",
        }
        limit = noise_limits.get(jurisdiction, "check state regulations")
        return (
            ComplianceStatus.CONDITIONAL,
            ["ADR 28/01"],
            ["VSB 6 Section 8"],
            f"Noise limit: {limit}. Aftermarket exhaust must not exceed factory dB level "
            f"plus 3dB tolerance. Cat-back only for basic compliance.",
        )

    # Engine performance — forced induction, ECU tuning
    if cat == "performance" or cat == "engine":
        return (
            ComplianceStatus.CONDITIONAL,
            ["ADR 79/01", "ADR 79/02"],
            ["VSB 6 Section 6"],
            "Engine/ECU modifications require ADR 79/01 emission compliance. "
            "Forced induction changes must be reported to insurer and may affect registration.",
        )

    # Audio — aftermarket head units, speakers, subwoofers
    if cat == "audio":
        return (
            ComplianceStatus.CONDITIONAL,
            ["ADR 42/00"],
            [],
            "Aftermarket audio must comply with ADR 42/00 (vehicle noise). "
            "Subwoofers exceeding 100W RMS may require compliance certificate.",
        )

    # Visual — lights, tint, external accessories
    if cat == "visual" or cat == "exterior":
        return (
            ComplianceStatus.CONDITIONAL,
            ["ADR 13/00", "ADR 14/00", "ADR 48/00"],
            ["VSB 6 Section 9"],
            "Light/visibility modifications must comply with ADR 13/00 (tint) and ADR 14/00 (lights). "
            "Window tint: min 35% VLT front, min 20% VLT rear.",
        )

    # Interior — roll cages, race seats
    if cat == "interior":
        return (
            ComplianceStatus.CONDITIONAL,
            ["ADR 3/03"],
            ["VSB 6 Section 4"],
            "Interior modifications affecting occupant protection require ADR 3/03 compliance.",
        )

    # Wheels and tyres
    if "wheel" in name_lower or "tyre" in name_lower or "tire" in name_lower:
        return (
            ComplianceStatus.CONDITIONAL,
            ["ADR 23/00", "ADR 24/00"],
            ["VSB 6 Section 3"],
            "Wheel/tyre changes must fit within the manufacturer's approved size range "
            "and maintain load rating. Wider track may require engineer sign-off.",
        )

    # Cosmetic / minor — decals, seat covers, floor mats
    if cat == "other" or cat == "cosmetic":
        return (
            ComplianceStatus.PASS,
            [],
            [],
            "Cosmetic modifications are generally compliant without certification.",
        )

    # Default: moderate risk
    return (
        ComplianceStatus.CONDITIONAL,
        [],
        [],
        "Review recommended. This modification category may require compliance assessment.",
    )


def _evaluate_import_pathway(
    vin: str, jurisdiction: str
) -> tuple[str, str, dict, list[str]]:
    """Evaluate import compliance pathway for a VIN.

    Deterministic. Uses VIN prefix heuristics for vehicle origin country.
    """
    if len(vin) < 3:
        return ("unknown", "insufficient_data", {}, [])

    # VIN country codes (first character)
    country_code = vin[0].upper()
    country_map = {
        "J": "Japan",
        "S": "United Kingdom",
        "W": "Germany",
        "Z": "Italy",
        "K": "South Korea",
        "L": "China",
        "M": "India",
        "T": "Thailand",
        "V": "France/Spain",
        "Y": "Sweden/Finland",
    }
    origin_country = country_map.get(country_code, "Unknown")

    # US/Canada vehicles (1/4 prefix) — different compliance track
    if country_code in ("1", "4", "5"):
        pathway_type = "sevs"
        eligibility = "conditional"
        requirements = {
            "steps": [
                "Apply to SEVS (Specialist and Enthusiast Vehicle Scheme)",
                "Obtain NVA (New Vehicle Approval) if applicable",
                "Import through approved import agent",
                "Complete ADR compliance assessment",
                "Register with state transport authority",
            ],
            "documents": [
                "Import approval (DAF/SEVS)",
                "Compliance plate documentation",
                "ADR compliance certificate",
                "Engineering assessment report",
                "Vehicle identification check (stat dec)",
                "Customs clearance",
                "GST/Duty payment receipt",
            ],
        }
        adr = ["ADR 1-85 (full ADR compliance)"]
    elif origin_country in ("Japan", "Thailand", "South Korea", "India"):
        pathway_type = "raws"
        eligibility = "eligible"
        requirements = {
            "steps": [
                "Verify vehicle meets RAV (Register of Approved Vehicles)",
                "Confirm age restriction (15+ years or RAV listed)",
                "Import through registered customs broker",
                "Complete ADR compliance assessment",
                "Register with state transport authority",
            ],
            "documents": [
                "RAV listing confirmation",
                "Import approval (DAF)",
                "ADR compliance certificate",
                "Vehicle identification check (stat dec)",
                "Customs clearance",
                "GST/Duty payment receipt",
            ],
        }
        adr = ["ADR 1-85 (applicable ADRs for vehicle age)"]
    elif origin_country in ("Germany", "United Kingdom", "France/Spain", "Italy", "Sweden/Finland"):
        pathway_type = "personal_import"
        eligibility = "eligible"
        requirements = {
            "steps": [
                "Verify vehicle eligibility for personal import",
                "Obtain European compliance documentation (if available)",
                "Import through registered customs broker",
                "Complete ADR compliance assessment",
                "Register with state transport authority",
            ],
            "documents": [
                "European Certificate of Conformity (if available)",
                "Import approval (DAF)",
                "ADR compliance certificate",
                "Vehicle identification check (stat dec)",
                "Customs clearance",
                "GST/Duty payment receipt",
            ],
        }
        adr = ["ADR 1-85 (applicable ADRs)"]
    else:
        pathway_type = "assessment_required"
        eligibility = "assessment_required"
        requirements = {
            "steps": [
                "Contact transport authority for import eligibility assessment",
                "Engage a VASS engineer for pre-assessment",
                "Determine applicable ADR requirements",
                "Complete compliance pathway",
            ],
            "documents": [
                "Vehicle specification sheet",
                "Country of origin compliance certificate",
                "Engineering assessment (preliminary)",
            ],
        }
        adr = []

    return (pathway_type, eligibility, requirements, adr)


def _build_document_checklist(pathway: ImportPathway) -> list[DocumentChecklistItem]:
    """Build a document checklist from pathway requirements."""
    if not pathway.requirements_json:
        return []
    docs = pathway.requirements_json.get("documents", [])
    return [
        DocumentChecklistItem(name=doc, required=True)
        for doc in docs
    ]


# ---------------------------------------------------------------------------
# Vehicle make/model/year lookup
# ---------------------------------------------------------------------------

@router.get("/vehicle-lookup/makes")
async def list_vehicle_makes() -> list[str]:
    """List all vehicle makes in the compliance database."""
    return get_available_makes()


@router.get("/vehicle-lookup/models/{make}")
async def list_vehicle_models(make: str) -> list[str]:
    """List available models for a given make."""
    models = get_models_for_make(make)
    if not models:
        raise HTTPException(status_code=404, detail=f"No models found for make '{make}'")
    return models


@router.get("/vehicle-lookup/year-range")
async def get_vehicle_year_range(
    make: str = Query(..., min_length=1),
    model: str = Query(..., min_length=1),
) -> dict:
    """Get the year range for a specific make/model."""
    return get_year_range(make, model)


@router.post("/vehicle-lookup", response_model=VehicleLookupResponse)
async def vehicle_lookup(
    payload: VehicleLookupRequest,
) -> VehicleLookupResponse:
    """Look up vehicles by make, model, and year.

    Returns matching vehicles from the Australian compliance database.
    """
    results = lookup_vehicle(
        make=payload.make,
        model=payload.model,
        year=payload.year,
    )
    return VehicleLookupResponse(
        vehicles=[VehicleLookupItem(**v) for v in results],
        total=len(results),
        make=payload.make,
        model=payload.model,
        year=payload.year,
    )


# ---------------------------------------------------------------------------
# VIN validation
# ---------------------------------------------------------------------------

@router.post("/vin/validate", response_model=VinValidationResponse)
async def validate_vin_endpoint(
    payload: VinValidationRequest,
) -> VinValidationResponse:
    """Validate a 17-character VIN per ISO 3779 with AU heuristics.

    Checks format, allowed characters, WMI prefix, model year code,
    and optional check-digit validation.
    """
    vin = payload.vin.upper().strip()
    is_valid, errors = validate_vin(vin)
    check_digit = validate_check_digit(vin) if is_valid else None

    manufacturer = None
    country = None
    year = None
    rhd = None

    if is_valid:
        try:
            decoded = decode_vin(vin)
            manufacturer = decoded.get("manufacturer")
            country = decoded.get("country")
            year = decoded.get("year")
            rhd = decoded.get("is_right_hand_drive")
        except ValueError:
            pass

    return VinValidationResponse(
        vin=vin,
        is_valid=is_valid,
        errors=errors,
        check_digit_valid=check_digit,
        manufacturer=manufacturer,
        country=country,
        year=year,
        is_right_hand_drive=rhd,
    )


# ---------------------------------------------------------------------------
# Modification checklist generation
# ---------------------------------------------------------------------------

@router.post("/modification-checklist", response_model=ModificationChecklistResponse)
async def generate_modification_checklist_endpoint(
    payload: ModificationChecklistRequest,
) -> ModificationChecklistResponse:
    """Generate a compliance checklist for a set of modifications.

    Deterministic rule engine — no AI dependency. Returns checklist items
    with applicable ADR/VSB references and estimated costs.
    """
    mods = [m.model_dump() for m in payload.modifications]
    items = generate_modification_checklist(
        modifications=mods,
        vehicle_category=payload.vehicle_category,
        jurisdiction=payload.jurisdiction.value if hasattr(payload.jurisdiction, "value") else str(payload.jurisdiction),
    )

    total_cost = sum(item.est_cost_aud or 0 for item in items)
    required_count = sum(1 for item in items if item.required)

    return ModificationChecklistResponse(
        modifications=payload.modifications,
        vehicle_category=payload.vehicle_category,
        jurisdiction=payload.jurisdiction.value if hasattr(payload.jurisdiction, "value") else str(payload.jurisdiction),
        checklist=[ChecklistItemOut(**item.__dict__) for item in items],
        total_items=len(items),
        required_items=required_count,
        est_total_cost_aud=total_cost,
    )


# ---------------------------------------------------------------------------
# Compliance results aggregation
# ---------------------------------------------------------------------------

@router.post("/compliance/aggregate", response_model=ComplianceAggregationResponse)
async def aggregate_compliance_results_endpoint(
    payload: ComplianceAggregationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ComplianceAggregationResponse:
    """Aggregate compliance results for a precheck session.

    Returns an overall score, pass/fail breakdown, and per-modification details.
    """
    precheck = await db.get(VassPrecheck, payload.precheck_id)
    if not precheck or precheck.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pre-check not found")

    results = list(await db.scalars(
        select(ComplianceResult)
        .where(ComplianceResult.precheck_id == payload.precheck_id)
        .order_by(ComplianceResult.created_at)
    ))

    agg = aggregate_compliance_results(results)
    return ComplianceAggregationResponse(**agg)


@router.get("/compliance/aggregate/{precheck_id}", response_model=ComplianceAggregationResponse)
async def get_compliance_aggregation(
    precheck_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ComplianceAggregationResponse:
    """GET variant — aggregate compliance results for a precheck."""
    precheck = await db.get(VassPrecheck, precheck_id)
    if not precheck or precheck.user_id != user.id:
        raise HTTPException(status_code=404, detail="Pre-check not found")

    results = list(await db.scalars(
        select(ComplianceResult)
        .where(ComplianceResult.precheck_id == precheck_id)
        .order_by(ComplianceResult.created_at)
    ))

    agg = aggregate_compliance_results(results)
    return ComplianceAggregationResponse(**agg)