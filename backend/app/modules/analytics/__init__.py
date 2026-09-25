"""Analytics module contract.

This module defines the public interface for vehicle analytics and reporting.
Actual implementations live in:
- app.api.v1.analytics (analytics endpoint)
- app.schemas.analytics (AnalyticsResponse, CostForecast, SpendSummary)
- app.models.ha (Home Assistant analytics integration)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.ha import HaIntegration
    from app.schemas.analytics import AnalyticsResponse, CostForecast, MonthlySpend, SpendSummary

__all__ = [
    "AnalyticsResponse",
    "CostForecast",
    "MonthlySpend",
    "SpendSummary",
    "HaIntegration",
    "analytics",
]


def __getattr__(name: str):
    if name in {"AnalyticsResponse", "CostForecast", "MonthlySpend", "SpendSummary"}:
        from app.schemas.analytics import AnalyticsResponse, CostForecast, MonthlySpend, SpendSummary
        globals().update({
            "AnalyticsResponse": AnalyticsResponse,
            "CostForecast": CostForecast,
            "MonthlySpend": MonthlySpend,
            "SpendSummary": SpendSummary,
        })
        return globals()[name]
    if name == "HaIntegration":
        from app.models.ha import HaIntegration
        globals()["HaIntegration"] = HaIntegration
        return HaIntegration
    if name == "analytics":
        from app.api.v1.analytics import analytics
        globals()["analytics"] = analytics
        return analytics
    raise AttributeError(f"module 'app.modules.analytics' has no attribute '{name}'")