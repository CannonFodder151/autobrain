"""Fuel tracking and analytics module contract.

Actual implementations live in:
- app.services.fuel (business logic: efficiency, stats, receipt intake)
- app.services.fuel_prices (price data)
- app.services.fuel_feeds (feed ingestion)
- app.services.fuel_servo (station mapping)
"""

__all__ = [
    "compute_fuel_stats",
    "recompute_efficiency",
    "link_receipt",
    "extract_fuel_receipt",
]


def __getattr__(name: str):
    if name in __all__:
        from app.services.fuel import (
            compute_fuel_stats,
            recompute_efficiency,
            link_receipt,
            extract_fuel_receipt,
        )
        globals().update({
            "compute_fuel_stats": compute_fuel_stats,
            "recompute_efficiency": recompute_efficiency,
            "link_receipt": link_receipt,
            "extract_fuel_receipt": extract_fuel_receipt,
        })
        return globals()[name]
    raise AttributeError(f"module 'app.modules.fuel' has no attribute '{name}'")