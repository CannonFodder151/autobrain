from __future__ import annotations

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class VassVehicle:
    base_vehicle_id: str
    make: str
    model: str
    year: int
    vin_prefix: Optional[str] = None
    compliance_status: str = "unknown"


@dataclass
class VinInfo:
    vin: str
    valid: bool
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    body_style: Optional[str] = None
    engine: Optional[str] = None
    country: Optional[str] = None
    errors: List[str] = field(default_factory=list)


@dataclass
class ChecklistItem:
    id: str
    category: str
    description: str
    required: bool = True
    status: str = "pending"
    notes: Optional[str] = None


@dataclass
class ComplianceResult:
    vehicle_id: str
    overall_status: str
    score: float
    passed: int
    failed: int
    total: int
    details: List[Dict[str, Any]] = field(default_factory=list)


_VEHICLES: Dict[str, VassVehicle] = {}
_CHECKLISTS: Dict[str, List[ChecklistItem]] = {}


def _vkey(make: str, model: str, year: int) -> str:
    return f"{make.lower()}|{model.lower()}|{year}"


# seed
def _seed():
    if not _VEHICLES:
        v = VassVehicle(base_vehicle_id="BV001", make="Toyota", model="Hilux", year=2020, vin_prefix="MR0", compliance_status="compliant")
        _VEHICLES[_vkey("Toyota", "Hilux", 2020)] = v
        v2 = VassVehicle(base_vehicle_id="BV002", make="Ford", model="Ranger", year=2019, vin_prefix="1FT", compliance_status="needs_review")
        _VEHICLES[_vkey("Ford", "Ranger", 2019)] = v2


_seed()


def lookup_vehicle(make: str, model: str, year: int) -> Optional[VassVehicle]:
    return _VEHICLES.get(_vkey(make, model, year))


def decode_vin(vin: str) -> VinInfo:
    errors = []
    if not vin or len(vin) != 17:
        errors.append("VIN must be 17 characters")
        return VinInfo(vin=vin, valid=False, errors=errors)
    # basic structure check
    if vin[0] not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
        errors.append("Invalid VIN characters")
    valid = len(errors) == 0
    if valid:
        # fake decode
        if vin.startswith("MR0"):
            return VinInfo(vin=vin, valid=True, make="Toyota", model="Hilux", year=2020, body_style="Ute", engine="2.8D", country="TH")
        if vin.startswith("1FT"):
            return VinInfo(vin=vin, valid=True, make="Ford", model="Ranger", year=2019, body_style="Ute", engine="2.0T", country="US")
    return VinInfo(vin=vin, valid=valid, errors=errors)


def generate_checklist(vehicle_id: str, modifications: List[str]) -> List[ChecklistItem]:
    items = []
    if not modifications:
        items = [
            ChecklistItem(id="ch001", category="Lighting", description="Check headlight compliance", required=True),
            ChecklistItem(id="ch002", category="Brakes", description="Brake system inspection", required=True),
            ChecklistItem(id="ch003", category="Emissions", description="Emissions compliance check", required=True),
        ]
    else:
        items = [
            ChecklistItem(id="ch100", category="Lighting", description="Check modified lighting compliance", required=True),
            ChecklistItem(id="ch101", category="Suspension", description="Suspension modification compliance", required=True),
            ChecklistItem(id="ch102", category="Tires/Wheels", description="Wheel/tire fitment compliance", required=True),
        ]
        for m in modifications:
            if "exhaust" in m.lower():
                items.append(ChecklistItem(id="ch200", category="Exhaust", description="Exhaust modification compliance", required=True))
            if "engine" in m.lower():
                items.append(ChecklistItem(id="ch201", category="Engine", description="Engine modification compliance", required=True))
    _CHECKLISTS[vehicle_id] = items
    return items


def aggregate_results(vehicle_id: str, results: List[Dict[str, Any]]) -> ComplianceResult:
    total = len(results)
    passed = sum(1 for r in results if r.get("status") == "pass")
    failed = sum(1 for r in results if r.get("status") == "fail")
    score = (passed / total * 100.0) if total else 0.0
    if failed == 0 and passed == total and total > 0:
        overall_status = "compliant"
    elif failed > 0:
        overall_status = "non_compliant"
    else:
        overall_status = "pending"
    return ComplianceResult(vehicle_id=vehicle_id, overall_status=overall_status, score=round(score, 2), passed=passed, failed=failed, total=total, details=results)
