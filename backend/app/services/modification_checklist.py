"""Modification checklist generator — deterministic, no AI.

Given a vehicle category and a list of modifications, produces a checklist
of required compliance items with applicable ADR/VSB references.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChecklistItem:
    id: str
    category: str
    name: str
    description: str
    required: bool = True
    adr_references: list[str] = field(default_factory=list)
    vsb_references: list[str] = field(default_factory=list)
    est_cost_aud: int | None = None
    notes: str | None = None


def generate_modification_checklist(
    modifications: list[dict],
    vehicle_category: str = "passenger",
    jurisdiction: str = "VIC",
) -> list[ChecklistItem]:
    """Generate a compliance checklist for a set of modifications.

    Each modification dict should have at least `name` and `category`.
    Vehicle category is passenger/light_truck/motorcycle/heavy_vehicle.
    """
    items: list[ChecklistItem] = []
    seen: set[str] = set()

    for mod in modifications:
        name = mod.get("name", "")
        cat = mod.get("category", "other").lower()

        new_items = _checklist_for_category(cat, name, jurisdiction, vehicle_category)
        for item in new_items:
            key = (item.name, item.category)
            if key not in seen:
                seen.add(key)
                items.append(item)

    # Universal items — always required regardless of mods
    for universal in _universal_items():
        key = (universal.name, universal.category)
        if key not in seen:
            seen.add(key)
            items.append(universal)

    return items


def _checklist_for_category(
    cat: str, name: str, jurisdiction: str, vehicle_category: str
) -> list[ChecklistItem]:
    name_lower = name.lower()

    if cat == "suspension":
        return [
            ChecklistItem(
                id="SUS-001", category="suspension", name="Suspension compliance check",
                description="Verify vehicle height within ±25mm of ADR compliance height. "
                            "Coilovers and lift kits require engineer certification.",
                adr_references=["ADR 01/00", "ADR 02/00"],
                vsb_references=["VSB 6 Section 5"],
                est_cost_aud=500,
                notes="Coilovers and lift kits require VASS engineer sign-off.",
            ),
            ChecklistItem(
                id="SUS-002", category="suspension", name="Damper compliance",
                description="Aftermarket dampers must meet ADR 01/00 standards.",
                adr_references=["ADR 01/00"],
                required=False,
            ),
        ]

    if cat == "exhaust":
        noise_limits = {
            "VIC": "75dB(A) at 3000RPM", "NSW": "82dB(A) (driving test)",
            "QLD": "82dB(A) (driving test)", "SA": "75dB(A) at 3000RPM",
            "WA": "90dB(A) stationary", "TAS": "82dB(A) (driving test)",
            "ACT": "82dB(A) (driving test)", "NT": "90dB(A) stationary",
        }
        limit = noise_limits.get(jurisdiction, "check state regulations")
        return [
            ChecklistItem(
                id="EXH-001", category="exhaust", name="Noise compliance",
                description=f"Exhaust noise limit for {jurisdiction}: {limit}. "
                            "Cat-back only for basic compliance.",
                adr_references=["ADR 28/01"],
                vsb_references=["VSB 6 Section 8"],
                est_cost_aud=300,
                notes="Aftermarket exhaust must not exceed factory dB level plus 3dB.",
            ),
        ]

    if cat == "brakes":
        return [
            ChecklistItem(
                id="BRK-001", category="brakes", name="Brake system compliance",
                description="Brake modifications require VASS engineer sign-off. "
                            "Ensure matching caliper/rotor/drums to manufacturer spec.",
                adr_references=["ADR 31/04", "ADR 35/05"],
                vsb_references=["VSB 6 Section 7"],
                est_cost_aud=800,
            ),
            ChecklistItem(
                id="BRK-002", category="brakes", name="Brake test report",
                description="Independent brake test report required for brake system modifications.",
                adr_references=["ADR 31/04"],
                required=True,
            ),
        ]

    if cat == "engine" or cat == "performance":
        return [
            ChecklistItem(
                id="ENG-001", category="engine", name="Engine/ECU compliance",
                description="Engine/ECU modifications require ADR 79/01 emission compliance. "
                            "Forced induction must be reported to insurer.",
                adr_references=["ADR 79/01", "ADR 79/02"],
                vsb_references=["VSB 6 Section 6"],
                est_cost_aud=1200,
                notes="Turbo/supercharger kits require full ADR emission test.",
            ),
        ]

    if cat == "wheels" or cat == "wheels_tyres" or "wheel" in name_lower or "tyre" in name_lower or "tire" in name_lower:
        return [
            ChecklistItem(
                id="WHL-001", category="wheels", name="Wheel/tyre compliance",
                description="Wheel/tyre changes must fit within manufacturer's approved size range "
                            "and maintain load rating. Wider track may require engineer sign-off.",
                adr_references=["ADR 23/00", "ADR 24/00"],
                vsb_references=["VSB 6 Section 3"],
                est_cost_aud=200,
            ),
        ]

    if cat == "lighting" or cat == "visual" or cat == "exterior":
        return [
            ChecklistItem(
                id="VIS-001", category="visual", name="Light/visibility compliance",
                description="Light modifications must comply with ADR 13/00 (tint) and ADR 14/00 (lights). "
                            "Window tint: min 35% VLT front, min 20% VLT rear.",
                adr_references=["ADR 13/00", "ADR 14/00", "ADR 48/00"],
                vsb_references=["VSB 6 Section 9"],
                est_cost_aud=200,
            ),
        ]

    if cat == "body" or cat == "towing":
        return [
            ChecklistItem(
                id="BDY-001", category="body", name="Body/towing compliance",
                description="Body modifications must maintain structural integrity and occupant protection. "
                            "Tow bars must comply with ADR 62/00.",
                adr_references=["ADR 29/00", "ADR 62/00"],
                vsb_references=["VSB 6 Section 4"],
                est_cost_aud=600,
            ),
        ]

    if cat == "interior":
        return [
            ChecklistItem(
                id="INT-001", category="interior", name="Interior compliance",
                description="Interior modifications affecting occupant protection require ADR 3/03 compliance.",
                adr_references=["ADR 3/03"],
                vsb_references=["VSB 6 Section 4"],
                est_cost_aud=400,
            ),
        ]

    if cat == "audio":
        return [
            ChecklistItem(
                id="AUD-001", category="audio", name="Audio compliance",
                description="Aftermarket audio must comply with ADR 42/00 (vehicle noise). "
                            "Subwoofers exceeding 100W RMS may require compliance certificate.",
                adr_references=["ADR 42/00"],
                est_cost_aud=100,
            ),
        ]

    # Default: cosmetic / other
    return [
        ChecklistItem(
            id="OTH-001", category="other", name="Visual inspection",
            description="Cosmetic modification — visual inspection recommended.",
            required=False,
            est_cost_aud=0,
            notes="Cosmetic modifications are generally compliant without certification.",
        ),
    ]


def _universal_items() -> list[ChecklistItem]:
    return [
        ChecklistItem(
            id="UID-001", category="identity", name="VIN verification",
            description="Verify VIN plate is legible and matches registration.",
            adr_references=[],
        ),
        ChecklistItem(
            id="UID-002", category="identity", name="Compliance plate check",
            description="Confirm compliance plate is present and legible "
                        "(if vehicle was imported or originally compliant).",
            adr_references=[],
        ),
    ]
