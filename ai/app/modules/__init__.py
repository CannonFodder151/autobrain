"""AI modules package."""

from ai.app.modules.diagnostics import AIDiagnosticsScorer
from ai.app.modules.health_score import AIVehicleHealthScorer
from ai.app.modules.service_prediction import AIServicePredictionScorer

__all__ = [
    "AIVehicleHealthScorer",
    "AIDiagnosticsScorer",
    "AIServicePredictionScorer",
]