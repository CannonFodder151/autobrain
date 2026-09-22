"""Deterministic VASS mod-legality fallback.

Rule-based compliance lookup per Australian state/territory. Produces the same
output schema as the router path so callers cannot tell the difference when the
9Router is unreachable.
"""

# Known illegal / conditionally-legal modifications by category + keywords.
# Each entry: (status, references, restriction_summary, keywords)
# status: "legal" | "non_compliant" | "conditional" | "requires_engineer"
_MOD_LEGALITY_TABLE: dict[str, tuple[str, list[str], str, list[str]]] = {
    "exhaust": (
        "non_compliant",
        ["ADR 83", "ADR 79", "VSB 6 Section 2"],
        "Catalytic converter or DPF removal is illegal; cat-back exhausts must retain the catalytic converter.",
        ["cat", "catalyst", "dpf", "diesel particulate", "remove"],
    ),
    "lighting": (
        "non_compliant",
        ["ADR 13", "ADR 45", "ADR 46", "ADR 47", "ADR 48", "ADR 49", "VSI 16"],
        "Aftermarket headlight/fog light aim changes, coloured HID kits, and LED bulbs in halogen housings are non-compliant.",
        ["hid", "led", "headlight", "fog", "aim", "coloured", "rgb"],
    ),
    "wheels_tyres": (
        "conditional",
        ["ADR 23", "ADR 24", "VSB 6 Section 7"],
        "Wheel/tyre changes must not cause the tyre to contact the body or exceed the original overall diameter by more than 15mm.",
        ["size", "diameter", "width", "offset", "staggered"],
    ),
    "engine": (
        "requires_engineer",
        ["ADR 30", "ADR 36", "ADR 79", "VSB 6 Section 1", "VSI 8", "VSI 9"],
        "Engine swaps and forced-induction conversions require a VASS engineering certificate.",
        ["swap", "turbo", "supercharger", "forced induction", "stroker"],
    ),
    "brakes": (
        "conditional",
        ["ADR 31", "ADR 35", "VSB 6 Section 4"],
        "Aftermarket big-brake kits are generally compliant if they retain original brake balance; braided hoses are permitted.",
        ["big brake", "braided", "hose", "kit", "upgrade"],
    ),
    "suspension": (
        "conditional",
        ["ADR 43", "VSB 6 Section 3", "VSI 9", "VSI 13"],
        "Lowering/upgrading suspension is allowed within VSB 6 limits; excessive lowering may fail the 100mm ground-clearance rule.",
        ["coilover", "lowering", "lift", "air", "height"],
    ),
    "body": (
        "conditional",
        ["ADR 42", "ADR 43", "VSB 6 Section 6"],
        "Body kits, wide-body flares, and structural modifications may require engineering assessment.",
        ["wide body", "flares", "body kit", "structural", "chassis"],
    ),
    "emissions": (
        "non_compliant",
        ["ADR 79", "ADR 80", "VSB 6 Section 8"],
        "Emissions system tampering (EGR delete, secondary air pump removal, EVAP delete) is non-compliant.",
        ["egr", "evap", "secondary air", "delete", "tamper"],
    ),
    "performance": (
        "requires_engineer",
        ["ADR 30", "ADR 36", "VSB 6 Section 1"],
        "Performance ECU tunes that disable emissions controls or raise boost beyond design limits require engineering certification.",
        ["tune", "remap", "ecu", "boost", "chip", "flash"],
    ),
    "tint": (
        "conditional",
        ["ADR 13", "VSI 35/36"],
        "Window tint darkness is regulated by state: front side windows must allow ≥70% (VIC/NSW) or ≥75% VLT; rear may be darker.",
        ["tint", "window", "film", "dark"],
    ),
    "audio": (
        "legal",
        [],
        "Aftermarket audio installations are legal if mounted per manufacturer instructions and do not obstruct controls.",
        [],
    ),
    "visual": (
        "legal",
        [],
        "Cosmetic visual modifications (badges, wraps, diffusers) are generally legal if they do not impair lighting or visibility.",
        [],
    ),
    "interior": (
        "legal",
        [],
        "Interior upgrades (seats, steering wheels) are legal if AS/NZS seatbelt mounting and airbag compatibility are retained.",
        [],
    ),
    "exterior": (
        "legal",
        [],
        "Non-structural exterior modifications are generally legal if lighting and visibility are unimpaired.",
        [],
    ),
    "other": (
        "requires_engineer",
        [],
        "General / unclassified modifications typically require a VASS engineering assessment.",
        [],
    ),
}


def mod_legality_fallback(payload: dict) -> dict:
    """Deterministic mod-legality assessment.

    Payload fields:
      name, category, state_territory, vehicle (optional), notes (optional)
    """
    name = (payload.get("name") or "This modification").strip()
    cat = (payload.get("category") or "other").lower()
    notes = (payload.get("notes") or "").lower()
    state = payload.get("state_territory") or "VIC"

    entry = _MOD_LEGALITY_TABLE.get(cat, _MOD_LEGALITY_TABLE["other"])
    status, references, restriction, keywords = entry

    # If the mod text mentions specific illegal keywords, escalate to non_compliant.
    if keywords:
        if any(kw in notes for kw in keywords):
            status = "non_compliant"

    # Build the summary.
    summary = f"{name} ({cat}) in {state}: {restriction}"

    restrictions = []
    if status == "non_compliant":
        restrictions.append(restriction)
    elif status == "conditional":
        restrictions.append(restriction)
    elif status == "requires_engineer":
        restrictions.append(f"Installation requires a VASS-approved engineer certificate ({state}).")

    confidence = 0.95 if cat in _MOD_LEGALITY_TABLE else 0.5

    return {
        "is_legal": status in ("legal", "conditional"),
        "status": status,
        "summary": summary,
        "relevant_references": references,
        "restrictions": restrictions,
        "confidence": confidence,
        "model": "rule-based-fallback",
    }