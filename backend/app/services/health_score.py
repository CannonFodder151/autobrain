"""Vehicle Health Score computation service.

Deterministic, rule-based engine that fuses diagnostics (0-25),
maintenance (0-25), fuel efficiency (0-25), OBD codes (0-15), and
parts (0-10) into a single 0-100 score with predictive failure
alerts and confidence scoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Legacy generic health score (kept for backward compatibility)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HealthMetric:
    name: str
    value: float = 0.0
    weight: float = 0.0
    min_value: float = 0.0
    max_value: float = 100.0


@dataclass(frozen=True)
class HealthScoreResult:
    score: float
    metrics: Dict[str, float]
    details: Dict[str, Dict[str, float]]


DEFAULT_METRICS: List[HealthMetric] = [
    HealthMetric(name="cpu_usage", weight=0.25, min_value=0.0, max_value=100.0),
    HealthMetric(name="memory_usage", weight=0.25, min_value=0.0, max_value=100.0),
    HealthMetric(name="disk_usage", weight=0.20, min_value=0.0, max_value=100.0),
    HealthMetric(name="network_latency", weight=0.15, min_value=0.0, max_value=500.0),
    HealthMetric(name="error_rate", weight=0.15, min_value=0.0, max_value=10.0),
]


def normalize_value(value: float, min_val: float, max_val: float) -> float:
    if max_val == min_val:
        return 1.0
    normalized = (value - min_val) / (max_val - min_val)
    return max(0.0, min(1.0, normalized))


def compute_health_score(
    metrics: Dict[str, float],
    metric_definitions: Optional[List[HealthMetric]] = None,
) -> HealthScoreResult:
    definitions = metric_definitions or DEFAULT_METRICS
    total_weight = sum(m.weight for m in definitions)
    if total_weight == 0:
        return HealthScoreResult(score=100.0, metrics={}, details={})

    metric_scores: Dict[str, float] = {}
    details: Dict[str, Dict[str, float]] = {}
    weighted_sum = 0.0

    for definition in definitions:
        raw_value = metrics.get(definition.name, definition.min_value)
        normalized = normalize_value(raw_value, definition.min_value, definition.max_value)
        inverted = 1.0 - normalized
        metric_score = inverted * 100.0
        metric_scores[definition.name] = metric_score
        details[definition.name] = {
            "raw_value": raw_value,
            "normalized": normalized,
            "score": metric_score,
            "weight": definition.weight,
        }
        weighted_sum += metric_score * definition.weight

    final_score = weighted_sum / total_weight
    return HealthScoreResult(
        score=round(final_score, 2),
        metrics=metric_scores,
        details=details,
    )


def get_health_status(score: float) -> str:
    if score >= 90:
        return "healthy"
    elif score >= 70:
        return "degraded"
    elif score >= 50:
        return "unhealthy"
    else:
        return "critical"


# ---------------------------------------------------------------------------
# Vehicle Health Score Engine
# ---------------------------------------------------------------------------

class VehicleHealthLabel(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


@dataclass(frozen=True)
class VehicleTelemetry:
    """Raw telemetry input for vehicle health scoring."""

    vehicle_id: str = ""
    # Diagnostics (0-25)
    dtcs: List[str] = field(default_factory=list)
    sensor_anomalies: int = 0
    # Maintenance (0-25)
    current_mileage: float = 0.0
    last_service_mileage: float = 0.0
    service_interval_km: float = 10000.0
    # Fuel efficiency (0-25)
    fuel_consumption_l_per_100km: Optional[float] = None
    fuel_level_pct: Optional[float] = None
    fuel_efficiency_trend: float = 0.0
    # OBD codes (0-15)
    obd_codes: List[str] = field(default_factory=list)
    # Parts (0-10)
    brake_wear_pct: float = 100.0
    battery_health_pct: float = 100.0
    tire_tread_depth_mm: float = 8.0
    engine_performance_pct: float = 100.0
    transmission_health_pct: float = 100.0
    suspension_health_pct: float = 100.0


@dataclass(frozen=True)
class ComponentScore:
    name: str
    score: float
    weight: float
    max_points: float
    raw_value: Optional[float] = None
    details: Optional[str] = None


@dataclass(frozen=True)
class PredictiveAlert:
    component: str
    severity: str
    message: str
    predicted_failure_km: Optional[float] = None
    confidence: float = 0.0


@dataclass(frozen=True)
class VehicleHealthScoreResult:
    vehicle_id: str
    overall_score: float
    label: VehicleHealthLabel
    components: Dict[str, ComponentScore]
    alerts: List[PredictiveAlert]
    confidence: float
    last_updated: str
    mileage: Optional[float] = None


class VehicleHealthScoreEngine:
    """Deterministic rule-based vehicle health score engine (0-100)."""

    def compute(self, telemetry: VehicleTelemetry) -> VehicleHealthScoreResult:
        now = datetime.now(timezone.utc).isoformat()

        diagnostics = self._score_diagnostics(telemetry)
        maintenance = self._score_maintenance(telemetry)
        fuel = self._score_fuel_efficiency(telemetry)
        obd = self._score_obd(telemetry)
        parts = self._score_parts(telemetry)

        components = {
            "diagnostics": diagnostics,
            "maintenance": maintenance,
            "fuel_efficiency": fuel,
            "obd_codes": obd,
            "parts": parts,
        }

        overall = (
            diagnostics.score + maintenance.score + fuel.score + obd.score + parts.score
        )
        overall = round(max(0.0, min(100.0, overall)), 1)

        return VehicleHealthScoreResult(
            vehicle_id=telemetry.vehicle_id,
            overall_score=overall,
            label=self._label(overall),
            components=components,
            alerts=self._predictive_alerts(telemetry, components),
            confidence=self._compute_confidence(telemetry),
            last_updated=now,
            mileage=telemetry.current_mileage,
        )

    def _score_diagnostics(self, t: VehicleTelemetry) -> ComponentScore:
        dtc_count = len(t.dtcs)
        anomaly_count = t.sensor_anomalies
        dtc_penalty = min(dtc_count * 2.0, 12.5)
        anomaly_penalty = min(anomaly_count * 3.0, 12.5)
        score = max(0.0, 25.0 - dtc_penalty - anomaly_penalty)
        details_parts = []
        if dtc_count > 0:
            details_parts.append(f"{dtc_count} DTC(s)")
        if anomaly_count > 0:
            details_parts.append(f"{anomaly_count} sensor anomaly(s)")
        return ComponentScore(
            name="diagnostics",
            score=round(score, 1),
            weight=0.25,
            max_points=25.0,
            raw_value=float(dtc_count + anomaly_count),
            details="; ".join(details_parts) if details_parts else "All systems normal",
        )

    def _score_maintenance(self, t: VehicleTelemetry) -> ComponentScore:
        if t.service_interval_km <= 0:
            return ComponentScore(
                name="maintenance",
                score=25.0,
                weight=0.25,
                max_points=25.0,
                raw_value=None,
                details="Service interval unavailable",
            )

        due_at = t.last_service_mileage + t.service_interval_km
        remaining = due_at - t.current_mileage

        if remaining <= 0:
            overdue_km = abs(remaining)
            penalty = min(overdue_km / t.service_interval_km * 25.0, 25.0)
            score = max(0.0, 25.0 - penalty)
            return ComponentScore(
                name="maintenance",
                score=round(score, 1),
                weight=0.25,
                max_points=25.0,
                raw_value=remaining,
                details=f"Service overdue by {overdue_km:.0f} km",
            )
        if remaining <= 1000:
            return ComponentScore(
                name="maintenance",
                score=20.0,
                weight=0.25,
                max_points=25.0,
                raw_value=remaining,
                details=f"Service due in {remaining:.0f} km",
            )
        return ComponentScore(
            name="maintenance",
            score=25.0,
            weight=0.25,
            max_points=25.0,
            raw_value=remaining,
            details=f"Service on track, next in {remaining:.0f} km",
        )

    def _score_fuel_efficiency(self, t: VehicleTelemetry) -> ComponentScore:
        if t.fuel_consumption_l_per_100km is None:
            return ComponentScore(
                name="fuel_efficiency",
                score=25.0,
                weight=0.25,
                max_points=25.0,
                raw_value=None,
                details="Fuel efficiency data unavailable",
            )

        consumption = t.fuel_consumption_l_per_100km
        if consumption <= 5.0:
            base_score = 25.0
        elif consumption <= 8.0:
            base_score = 22.0
        elif consumption <= 10.0:
            base_score = 20.0
        elif consumption <= 12.0:
            base_score = 15.0
        elif consumption <= 15.0:
            base_score = 10.0
        else:
            base_score = 5.0

        trend_penalty = max(0.0, -t.fuel_efficiency_trend) * 10.0
        score = max(0.0, base_score - trend_penalty)

        return ComponentScore(
            name="fuel_efficiency",
            score=round(score, 1),
            weight=0.25,
            max_points=25.0,
            raw_value=consumption,
            details=f"Consumption: {consumption:.1f} L/100km",
        )

    def _score_obd(self, t: VehicleTelemetry) -> ComponentScore:
        obd_count = len(t.obd_codes)
        if obd_count == 0:
            score = 15.0
            details = "No active OBD codes"
        elif obd_count == 1:
            score = 12.0
            details = f"{obd_count} active OBD code"
        elif obd_count <= 3:
            score = 8.0
            details = f"{obd_count} active OBD codes"
        else:
            score = 3.0
            details = f"{obd_count} active OBD codes"
        return ComponentScore(
            name="obd_codes",
            score=round(score, 1),
            weight=0.15,
            max_points=15.0,
            raw_value=float(obd_count),
            details=details,
        )

    def _score_parts(self, t: VehicleTelemetry) -> ComponentScore:
        parts = {
            "brakes": t.brake_wear_pct,
            "battery": t.battery_health_pct,
            "tires": min(t.tire_tread_depth_mm / 8.0 * 100.0, 100.0),
            "engine": t.engine_performance_pct,
            "transmission": t.transmission_health_pct,
            "suspension": t.suspension_health_pct,
        }
        avg_health = sum(parts.values()) / len(parts)
        score = avg_health / 100.0 * 10.0
        worst_part = min(parts, key=parts.get)
        worst_value = parts[worst_part]
        return ComponentScore(
            name="parts",
            score=round(score, 1),
            weight=0.10,
            max_points=10.0,
            raw_value=avg_health,
            details=f"Worst: {worst_part} at {worst_value:.0f}%",
        )

    def _label(self, score: float) -> VehicleHealthLabel:
        if score >= 90:
            return VehicleHealthLabel.EXCELLENT
        if score >= 75:
            return VehicleHealthLabel.GOOD
        if score >= 60:
            return VehicleHealthLabel.FAIR
        if score >= 40:
            return VehicleHealthLabel.POOR
        return VehicleHealthLabel.CRITICAL

    def _predictive_alerts(
        self,
        t: VehicleTelemetry,
        components: Dict[str, ComponentScore],
    ) -> List[PredictiveAlert]:
        alerts: List[PredictiveAlert] = []

        if t.brake_wear_pct <= 10:
            remaining_km = (t.brake_wear_pct / 100.0) * 50000
            alerts.append(PredictiveAlert(
                component="brakes",
                severity="critical",
                message=f"Brake pads critically worn ({t.brake_wear_pct:.0f}%). Immediate replacement recommended.",
                predicted_failure_km=remaining_km,
                confidence=0.9,
            ))
        elif t.brake_wear_pct <= 30:
            remaining_km = (t.brake_wear_pct / 100.0) * 50000
            alerts.append(PredictiveAlert(
                component="brakes",
                severity="warning",
                message=f"Brake pads wearing ({t.brake_wear_pct:.0f}%). Schedule replacement within {remaining_km:.0f} km.",
                predicted_failure_km=remaining_km,
                confidence=0.8,
            ))

        if t.battery_health_pct <= 20:
            alerts.append(PredictiveAlert(
                component="battery",
                severity="critical",
                message=f"Battery health critically low ({t.battery_health_pct:.0f}%). Immediate replacement recommended.",
                predicted_failure_km=None,
                confidence=0.85,
            ))
        elif t.battery_health_pct <= 50:
            alerts.append(PredictiveAlert(
                component="battery",
                severity="warning",
                message=f"Battery health declining ({t.battery_health_pct:.0f}%). Monitor closely.",
                predicted_failure_km=None,
                confidence=0.7,
            ))

        if t.tire_tread_depth_mm <= 2.0:
            alerts.append(PredictiveAlert(
                component="tires",
                severity="critical",
                message=f"Tire tread critically low ({t.tire_tread_depth_mm:.1f}mm). Replace immediately.",
                predicted_failure_km=0,
                confidence=0.95,
            ))
        elif t.tire_tread_depth_mm <= 4.0:
            remaining_km = (t.tire_tread_depth_mm - 1.6) / (8.0 - 1.6) * 80000
            alerts.append(PredictiveAlert(
                component="tires",
                severity="warning",
                message=f"Tire tread low ({t.tire_tread_depth_mm:.1f}mm). Replace within {remaining_km:.0f} km.",
                predicted_failure_km=remaining_km,
                confidence=0.8,
            ))

        due_at = t.last_service_mileage + t.service_interval_km
        remaining = due_at - t.current_mileage
        if remaining <= 0:
            alerts.append(PredictiveAlert(
                component="maintenance",
                severity="warning",
                message=f"Service overdue by {abs(remaining):.0f} km. Book service immediately.",
                predicted_failure_km=0,
                confidence=0.95,
            ))
        elif remaining <= 1000:
            alerts.append(PredictiveAlert(
                component="maintenance",
                severity="info",
                message=f"Service due in {remaining:.0f} km. Schedule soon.",
                predicted_failure_km=remaining,
                confidence=0.9,
            ))

        if len(t.dtcs) >= 3:
            alerts.append(PredictiveAlert(
                component="engine",
                severity="critical",
                message=f"Multiple DTCs detected ({len(t.dtcs)}). Immediate diagnostic required.",
                predicted_failure_km=0,
                confidence=0.85,
            ))
        elif len(t.dtcs) > 0:
            alerts.append(PredictiveAlert(
                component="engine",
                severity="warning",
                message=f"DTC(s) detected ({len(t.dtcs)}). Schedule diagnostic.",
                predicted_failure_km=1000,
                confidence=0.75,
            ))

        return alerts

    def _compute_confidence(self, t: VehicleTelemetry) -> float:
        factors = 0
        complete = 0

        if t.dtcs is not None:
            factors += 1
            complete += 1
        if t.current_mileage is not None:
            factors += 1
            complete += 1
        if t.fuel_consumption_l_per_100km is not None:
            factors += 1
            complete += 1
        if t.obd_codes is not None:
            factors += 1
            complete += 1
        if t.brake_wear_pct is not None:
            factors += 1
            complete += 1

        if factors == 0:
            return 0.0
        return round(min(1.0, complete / factors), 2)


# Singleton engine instance
vehicle_health_engine = VehicleHealthScoreEngine()


def compute_vehicle_health_score(
    telemetry: VehicleTelemetry,
) -> VehicleHealthScoreResult:
    """Convenience function to compute vehicle health score."""
    return vehicle_health_engine.compute(telemetry)
