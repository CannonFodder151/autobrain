"""Deterministic AI fallback for Vehicle Health Score computation."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class VehicleTelemetry:
    oil_pressure: float = 0.0
    tire_pressure: float = 0.0
    brake_wear: float = 0.0
    battery_health: float = 100.0
    engine_temp: float = 0.0
    coolant_temp: float = 0.0
    dtcs: List[str] = field(default_factory=list)
    service_interval_km: float = 10000.0
    current_mileage: float = 0.0


@dataclass(frozen=True)
class HealthFactor:
    name: str
    value: float
    weight: float
    score: float


@dataclass(frozen=True)
class HealthScoreResult:
    score: float
    status: str
    factors: Dict[str, HealthFactor]
    insights: Optional[List[str]] = None
    recommendations: Optional[List[str]] = None


WEIGHTS = {
    "oil": 0.20,
    "tires": 0.15,
    "brakes": 0.15,
    "battery": 0.15,
    "temps": 0.15,
    "dtcs": 0.10,
    "service_interval": 0.10,
}


def _normalize(val: float, min_v: float, max_v: float) -> float:
    if max_v == min_v:
        return 1.0
    n = (val - min_v) / (max_v - min_v)
    return max(0.0, min(1.0, n))


def compute_health_score(telemetry: VehicleTelemetry) -> HealthScoreResult:
    factors: Dict[str, HealthFactor] = {}

    oil_n = _normalize(telemetry.oil_pressure, 20.0, 80.0)
    oil_score = oil_n * 100.0
    factors["oil"] = HealthFactor("oil", telemetry.oil_pressure, WEIGHTS["oil"], oil_score)

    tire_n = _normalize(telemetry.tire_pressure, 28.0, 36.0)
    tire_score = tire_n * 100.0
    factors["tires"] = HealthFactor("tires", telemetry.tire_pressure, WEIGHTS["tires"], tire_score)

    brake_n = 1.0 - _normalize(telemetry.brake_wear, 0.0, 100.0)
    brake_score = brake_n * 100.0
    factors["brakes"] = HealthFactor("brakes", telemetry.brake_wear, WEIGHTS["brakes"], brake_score)

    battery_score = max(0.0, min(100.0, telemetry.battery_health))
    factors["battery"] = HealthFactor("battery", telemetry.battery_health, WEIGHTS["battery"], battery_score)

    engine_n = 1.0 - _normalize(telemetry.engine_temp, 70.0, 110.0)
    coolant_n = 1.0 - _normalize(telemetry.coolant_temp, 70.0, 110.0)
    temps_score = (engine_n + coolant_n) / 2.0 * 100.0
    factors["temps"] = HealthFactor("temps", (telemetry.engine_temp + telemetry.coolant_temp) / 2.0, WEIGHTS["temps"], temps_score)

    dtc_count = len(telemetry.dtcs)
    dtc_n = max(0.0, 1.0 - dtc_count / 5.0)
    dtc_score = dtc_n * 100.0
    factors["dtcs"] = HealthFactor("dtcs", float(dtc_count), WEIGHTS["dtcs"], dtc_score)

    remaining = max(0.0, telemetry.service_interval_km - telemetry.current_mileage)
    service_n = _normalize(remaining, 0.0, telemetry.service_interval_km)
    service_score = service_n * 100.0
    factors["service_interval"] = HealthFactor("service_interval", remaining, WEIGHTS["service_interval"], service_score)

    total_weight = sum(f.weight for f in factors.values())
    if total_weight == 0:
        score = 100.0
    else:
        score = sum(f.score * f.weight for f in factors.values()) / total_weight

    score = round(max(0.0, min(100.0, score)), 2)
    if score >= 90:
        status = "excellent"
    elif score >= 75:
        status = "good"
    elif score >= 60:
        status = "fair"
    elif score >= 40:
        status = "poor"
    else:
        status = "critical"

    return HealthScoreResult(score=score, status=status, factors=factors)


calculate_health_score = compute_health_score
calculate_deterministic_score = compute_health_score


if __name__ == "__main__":
    t = VehicleTelemetry(oil_pressure=65, tire_pressure=32, brake_wear=15, battery_health=90, engine_temp=85, coolant_temp=82, dtcs=[], service_interval_km=10000, current_mileage=2000)
    r = compute_health_score(t)
    print(r.score, r.status)
    assert r.score > 0
    print("ok")
