"""VASS (Vehicle Assessment Safety System) service.

Deterministic rule-based compliance checks for Australian vehicle modifications.
Rules are stored in the database and seeded from known ADR/VSI/VSB6 standards.
"""

import json
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vass import (
    VASRule,
    VASCheck,
    VehicleClass,
    StandardType,
    ModificationCategory,
    ComplianceStatus,
)
from app.schemas.vass import (
    VASCheckRequest,
    VASCheckResponse,
    VASSeedRule,
)


# Category aliases for flexible matching
CATEGORY_ALIASES: Dict[str, ModificationCategory] = {
    # Engine/performance
    "turbo": ModificationCategory.ENGINE,
    "turbocharged": ModificationCategory.ENGINE,
    "supercharger": ModificationCategory.ENGINE,
    "exhaust": ModificationCategory.ENGINE,
    "intake": ModificationCategory.ENGINE,
    "ecu": ModificationCategory.ENGINE,
    "engine": ModificationCategory.ENGINE,
    "engine_swap": ModificationCategory.ENGINE,
    "power": ModificationCategory.ENGINE,
    
    # Suspension
    "suspension": ModificationCategory.SUSPENSION,
    "lift_kit": ModificationCategory.SUSPENSION,
    "lift": ModificationCategory.SUSPENSION,
    "lowering": ModificationCategory.SUSPENSION,
    "coilovers": ModificationCategory.SUSPENSION,
    "springs": ModificationCategory.SUSPENSION,
    "shocks": ModificationCategory.SUSPENSION,
    "dropped": ModificationCategory.SUSPENSION,
    "raised": ModificationCategory.SUSPENSION,
    "body_lift": ModificationCategory.SUSPENSION,
    "suspension_lift": ModificationCategory.SUSPENSION,
    
    # Brakes
    "brakes": ModificationCategory.BRAKING,
    "brake": ModificationCategory.BRAKING,
    "brake_upgrade": ModificationCategory.BRAKING,
    "big_brakes": ModificationCategory.BRAKING,
    "slotted": ModificationCategory.BRAKING,
    "drilled": ModificationCategory.BRAKING,
    "calipers": ModificationCategory.BRAKING,
    
    # Lighting
    "lights": ModificationCategory.LIGHTING,
    "lighting": ModificationCategory.LIGHTING,
    "hid": ModificationCategory.LIGHTING,
    "hid_lights": ModificationCategory.LIGHTING,
    "xenon": ModificationCategory.LIGHTING,
    "led": ModificationCategory.LIGHTING,
    "led_lights": ModificationCategory.LIGHTING,
    "headlights": ModificationCategory.LIGHTING,
    "light_bar": ModificationCategory.LIGHTING,
    "lightbar": ModificationCategory.LIGHTING,
    "spotlights": ModificationCategory.LIGHTING,
    "auxiliary_lights": ModificationCategory.LIGHTING,
    "fog_lights": ModificationCategory.LIGHTING,
    "tail_lights": ModificationCategory.LIGHTING,
    
    # Body
    "body": ModificationCategory.BODY,
    "roll_cage": ModificationCategory.BODY,
    "bull_bar": ModificationCategory.BODY,
    "nudge_bar": ModificationCategory.BODY,
    "snorkel": ModificationCategory.BODY,
    "winch": ModificationCategory.BODY,
    "tray": ModificationCategory.BODY,
    "tub": ModificationCategory.BODY,
    "canopy": ModificationCategory.BODY,
    
    # Identification
    "vin": ModificationCategory.IDENTIFICATION,
    "identification": ModificationCategory.IDENTIFICATION,
    
    # Other
    "other": ModificationCategory.OTHER,
    "audio": ModificationCategory.OTHER,
    "visual": ModificationCategory.OTHER,
    "interior": ModificationCategory.OTHER,
    "exterior": ModificationCategory.OTHER,
}

# Vehicle class aliases
VEHICLE_CLASS_ALIASES: Dict[str, VehicleClass] = {
    "car": VehicleClass.PASS_CAR,
    "sedan": VehicleClass.PASS_CAR,
    "hatch": VehicleClass.PASS_CAR,
    "wagon": VehicleClass.PASS_CAR,
    "coupe": VehicleClass.PASS_CAR,
    "convertible": VehicleClass.PASS_CAR,
    "passenger": VehicleClass.PASS_CAR,
    "pass_car": VehicleClass.PASS_CAR,
    "ma": VehicleClass.PASS_CAR,
    
    "forward_control": VehicleClass.FORWARD_CONTROL,
    "mb": VehicleClass.FORWARD_CONTROL,
    "forward": VehicleClass.FORWARD_CONTROL,
    
    "off_road": VehicleClass.OFF_ROAD_PASS,
    "offroad": VehicleClass.OFF_ROAD_PASS,
    "4wd": VehicleClass.OFF_ROAD_PASS,
    "4x4": VehicleClass.OFF_ROAD_PASS,
    "suv": VehicleClass.OFF_ROAD_PASS,
    "mc": VehicleClass.OFF_ROAD_PASS,
    
    "light_truck": VehicleClass.LIGHT_TRUCK,
    "light_commercial": VehicleClass.LIGHT_TRUCK,
    "ute": VehicleClass.LIGHT_TRUCK,
    "van": VehicleClass.LIGHT_TRUCK,
    "na": VehicleClass.LIGHT_TRUCK,
    "truck": VehicleClass.LIGHT_TRUCK,
    "gvm": VehicleClass.LIGHT_TRUCK,
    
    "medium_truck": VehicleClass.MEDIUM_TRUCK,
    "nb": VehicleClass.MEDIUM_TRUCK,
    
    "heavy_truck": VehicleClass.HEAVY_TRUCK,
    "heavy": VehicleClass.HEAVY_TRUCK,
    "nc": VehicleClass.HEAVY_TRUCK,
    "prime_mover": VehicleClass.HEAVY_TRUCK,
    "semi": VehicleClass.HEAVY_TRUCK,
    
    "motorcycle": VehicleClass.MOTORCYCLE,
    "bike": VehicleClass.MOTORCYCLE,
    "la": VehicleClass.MOTORCYCLE,
    "lb": VehicleClass.MOTORCYCLE,
    "lc": VehicleClass.MOTORCYCLE,
    "ld": VehicleClass.MOTORCYCLE,
    
    "heavy_bus": VehicleClass.HEAVY_BUS,
    "bus": VehicleClass.HEAVY_BUS,
    "md": VehicleClass.HEAVY_BUS,
}


def normalize_category(raw: str) -> ModificationCategory:
    """Normalize a category string to a ModificationCategory enum."""
    key = raw.lower().strip().replace("-", "_").replace(" ", "_")
    return CATEGORY_ALIASES.get(key, ModificationCategory.OTHER)


def normalize_vehicle_class(raw: str) -> VehicleClass:
    """Normalize a vehicle class string to a VehicleClass enum."""
    key = raw.lower().strip().replace("-", "_").replace(" ", "_")
    return VEHICLE_CLASS_ALIASES.get(key, VehicleClass.PASS_CAR)


async def check_vass(
    db: AsyncSession,
    mod_category: str,
    mod_name: str,
    vehicle_class: str,
    mod_description: Optional[str] = None,
) -> VASCheckResponse:
    """Check a modification against VASS rules.
    
    Returns a deterministic result based on the rules table.
    """
    cat = normalize_category(mod_category)
    vclass = normalize_vehicle_class(vehicle_class)
    mod_name_lower = mod_name.lower().strip()
    
    # Query for matching rules
    query = select(VASRule).where(
        and_(
            VASRule.mod_category == cat,
            VASRule.vehicle_class == vclass,
            VASRule.is_active == True,
        )
    )
    result = await db.execute(query)
    rules = list(result.scalars().all())
    
    if not rules:
        # No rules found - default to conditional with note
        return VASCheckResponse(
            status=ComplianceStatus.CONDITIONAL,
            matched_rules=[],
            applied_standards=[],
            notes=f"No specific VASS rule found for {cat.value} modification on {vclass.value}. Manual engineering assessment recommended.",
            checked_at=datetime.utcnow(),
        )
    
    # Evaluate each matching rule
    matched_rules = []
    applied_standards = []
    overall_status = ComplianceStatus.PASS
    conditions = []
    notes = []
    
    for rule in rules:
        rule_dict = {
            "id": rule.id,
            "standard_ref": rule.standard_ref,
            "standard_section": rule.standard_section,
            "standard_title": rule.standard_title,
            "default_status": rule.default_status.value,
            "conditions": rule.conditions,
            "notes": rule.notes,
        }
        matched_rules.append(rule_dict)
        
        # Collect unique standard references
        if rule.standard_ref not in applied_standards:
            applied_standards.append(rule.standard_ref)
        
        # Determine overall status
        if rule.default_status == ComplianceStatus.FAIL:
            overall_status = ComplianceStatus.FAIL
        elif rule.default_status == ComplianceStatus.CONDITIONAL:
            overall_status = ComplianceStatus.CONDITIONAL
            if rule.conditions:
                conditions.append(rule.conditions)
        elif rule.default_status == ComplianceStatus.NOT_APPLICABLE:
            if overall_status != ComplianceStatus.FAIL:
                overall_status = ComplianceStatus.NOT_APPLICABLE
        
        if rule.notes:
            notes.append(rule.notes)
    
    return VASCheckResponse(
        status=overall_status,
        matched_rules=matched_rules,
        applied_standards=applied_standards,
        conditions_met=json.dumps(conditions) if conditions else None,
        notes="; ".join(notes) if notes else None,
        checked_at=datetime.utcnow(),
    )


async def seed_vass_rules(db: AsyncSession, rules: List[Dict[str, Any]]) -> int:
    """Seed VASS rules into the database.
    
    Args:
        db: Database session
        rules: List of rule dictionaries to insert
    
    Returns:
        Number of rules inserted
    """
    count = 0
    
    for rule_data in rules:
        # Check if rule already exists (by standard_ref + vehicle_class + mod_category)
        existing = await db.execute(
            select(VASRule).where(
                and_(
                    VASRule.standard_ref == rule_data["standard_ref"],
                    VASRule.vehicle_class == rule_data["vehicle_class"],
                    VASRule.mod_category == rule_data["mod_category"],
                )
            )
        )
        if existing.scalar_one_or_none():
            continue  # Skip duplicate
        
        rule = VASRule(**rule_data)
        db.add(rule)
        count += 1
    
    if count > 0:
        await db.commit()
    
    return count