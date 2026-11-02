"""VASS engineering helper: vehicle state → actionable plain-English guidance."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class VehicleState:
    vehicle_id: str
    engine_light_on: bool = False
    fault_codes: List[str] = field(default_factory=list)
    rego_expiry: Optional[str] = None
    rego_valid: bool = True
    current_mileage: Optional[int] = None
    last_service_mileage: Optional[int] = None
    service_interval_km: int = 10000
    ownership_status: str = "registered"
    fuel_level_pct: Optional[float] = None
    is_ev: bool = False
    is_phev: bool = False
    battery_soh_pct: Optional[float] = None
    range_km: Optional[int] = None


@dataclass
class Guidance:
    state: str
    severity: str  # info, warning, critical
    title: str
    message: str
    actions: List[str] = field(default_factory=list)


def _engine_light(state: VehicleState) -> Guidance:
    if not state.engine_light_on and not state.fault_codes:
        return Guidance("engine_light", "info", "Engine OK", "No engine faults detected.", [])
    codes = ", ".join(state.fault_codes) if state.fault_codes else "unknown"
    actions = ["Book a diagnostic scan", "Avoid heavy loads until checked"]
    if "P0" in codes:
        actions.append("Tow to workshop if flashing")
    return Guidance(
        "engine_light",
        "critical" if state.engine_light_on else "warning",
        "Engine light / fault codes",
        f"Engine light {'ON' if state.engine_light_on else 'off'}; fault codes: {codes}.",
        actions,
    )


def _rego(state: VehicleState) -> Guidance:
    if state.rego_valid:
        msg = "Registration is valid."
        if state.rego_expiry:
            msg += f" Expires {state.rego_expiry}."
        return Guidance("rego", "info", "Registration OK", msg, [])
    return Guidance(
        "rego",
        "critical",
        "Registration expired/invalid",
        f"Registration not valid (expiry: {state.rego_expiry or 'unknown'}).",
        ["Renew registration"],
    )


def _service(state: VehicleState) -> Guidance:
    if state.current_mileage is None or state.last_service_mileage is None:
        return Guidance("service_interval", "info", "Service status unknown", "Mileage data unavailable.", [])
    due_at = state.last_service_mileage + state.service_interval_km
    remaining = due_at - state.current_mileage
    if remaining <= 0:
        return Guidance(
            "service_interval",
            "warning",
            "Service overdue",
            f"Service overdue by {abs(remaining)} km.",
            ["Book a service now"],
        )
    if remaining <= 1000:
        return Guidance(
            "service_interval",
            "info",
            "Service due soon",
            f"Service due in {remaining} km.",
            ["Schedule service soon"],
        )
    return Guidance("service_interval", "info", "Service on track", f"Service on track, next in {remaining} km.", [])


def _ownership(state: VehicleState) -> Guidance:
    if state.ownership_status == "registered":
        return Guidance("ownership", "info", "Ownership OK", "Vehicle registered to current owner.", [])
    return Guidance(
        "ownership",
        "warning",
        "Ownership change pending",
        f"Ownership status: {state.ownership_status}.",
        ["Complete transfer paperwork"],
    )


def _fuel(state: VehicleState) -> Guidance:
    if state.fuel_level_pct is None:
        return Guidance("fuel", "info", "Fuel unknown", "Fuel level unavailable.", [])
    if state.fuel_level_pct < 15:
        return Guidance("fuel", "warning", "Low fuel", f"Fuel at {state.fuel_level_pct:.0f}%.", ["Refuel"])
    return Guidance("fuel", "info", "Fuel OK", f"Fuel at {state.fuel_level_pct:.0f}%.", [])


def _ev_powertrain(state: VehicleState) -> Guidance:
    if not (state.is_ev or state.is_phev):
        return Guidance("ev_powertrain", "info", "Not applicable", "Not applicable for internal combustion vehicle.", [])
    parts = []
    if state.battery_soh_pct is not None:
        parts.append(f"battery SOH {state.battery_soh_pct:.0f}%")
    if state.range_km is not None:
        parts.append(f"range {state.range_km} km")
    msg = "EV/PHEV: " + (", ".join(parts) if parts else "status unknown")
    sev = "warning" if (state.battery_soh_pct is not None and state.battery_soh_pct < 70) else "info"
    return Guidance("ev_powertrain", sev, "EV/PHEV powertrain", msg, [] if sev == "info" else ["Book battery health check"])


def compute_guidance(state: VehicleState) -> List[Guidance]:
    return [
        _engine_light(state),
        _rego(state),
        _service(state),
        _ownership(state),
        _fuel(state),
        _ev_powertrain(state),
    ]


def primary_guidance(guidances: List[Guidance]) -> Guidance:
    # most severe first
    order = {"critical": 0, "warning": 1, "info": 2}
    return min(guidances, key=lambda g: order.get(g.severity, 3))


def to_dict(g: Guidance) -> Dict[str, Any]:
    return {"state": g.state, "severity": g.severity, "title": g.title, "message": g.message, "actions": g.actions}


def generate_ai_explanation(state: VehicleState, primary: Guidance, model: Optional[Any] = None) -> Dict[str, Any]:
    """
    Generate AI-assisted explanation with deterministic fallback.
    Returns dict with 'explanation' (str) and 'used_fallback' (bool).
    """
    deterministic_explanation = _deterministic_explanation(state, primary)

    if model is None:
        return {"explanation": deterministic_explanation, "used_fallback": True, "reason": "model_not_configured"}

    try:
        raw = model.explain(state, primary)
    except Exception as exc:
        return {"explanation": deterministic_explanation, "used_fallback": True, "reason": f"model_exception:{exc}"}

    if not isinstance(raw, dict) or "explanation" not in raw:
        return {"explanation": deterministic_explanation, "used_fallback": True, "reason": "invalid_model_output"}

    explanation = raw["explanation"]
    if not isinstance(explanation, str) or not explanation.strip():
        return {"explanation": deterministic_explanation, "used_fallback": True, "reason": "empty_explanation"}

    return {"explanation": explanation, "used_fallback": False, "reason": None}


def _deterministic_explanation(state: VehicleState, primary: Guidance) -> str:
    """Deterministic fallback explanation - always produces an answer."""
    base = primary.message
    if primary.severity == "critical":
        base += " Immediate attention required."
    elif primary.severity == "warning":
        base += " Schedule attention soon."
    actions = primary.actions
    if actions:
        base += " " + " ".join(actions) + "."
    return base
