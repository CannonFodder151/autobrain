"""AI module wrapper for Vehicle Health Score.

Deterministic-first pattern with optional AI enhancement.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
    ai_summary: Optional[str] = None


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


def calculate_deterministic_score(telemetry: VehicleTelemetry) -> HealthScoreResult:
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


class HealthScoreCalculator:
    def __init__(self, ai_client: Optional[Any] = None):
        self.ai_client = ai_client

    def calculate(self, telemetry: VehicleTelemetry) -> HealthScoreResult:
        result = calculate_deterministic_score(telemetry)
        if self.ai_client is None:
            return result
        try:
            prompt = self._build_prompt(telemetry, result)
            response = self.ai_client.generate(prompt)
            insights = getattr(response, "insights", None) or response.get("insights") if isinstance(response, dict) else None
            recommendations = getattr(response, "recommendations", None) or response.get("recommendations") if isinstance(response, dict) else None
            ai_summary = getattr(response, "summary", None) or response.get("summary") if isinstance(response, dict) else None
            return HealthScoreResult(
                score=result.score,
                status=result.status,
                factors=result.factors,
                insights=insights,
                recommendations=recommendations,
                ai_summary=ai_summary,
            )
        except Exception:
            return result

    def _build_prompt(self, telemetry: VehicleTelemetry, result: HealthScoreResult) -> str:
        return (
            "Analyze vehicle health.\n"
            f"Score: {result.score} ({result.status})\n"
            f"Oil: {telemetry.oil_pressure}, Tires: {telemetry.tire_pressure}, "
            f"Brakes: {telemetry.brake_wear}%, Battery: {telemetry.battery_health}%, "
            f"Engine: {telemetry.engine_temp}C, Coolant: {telemetry.coolant_temp}C, "
            f"DTCs: {telemetry.dtcs}, Service km remaining: {max(0, telemetry.service_interval_km - telemetry.current_mileage)}\n"
            "Provide insights and recommendations."
        )


def calculate_health_score(telemetry: VehicleTelemetry, ai_client: Optional[Any] = None) -> HealthScoreResult:
    calculator = HealthScoreCalculator(ai_client=ai_client)
    return calculator.calculate(telemetry)
