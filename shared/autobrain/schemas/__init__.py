"""Shared schema package — contracts consumed by backend and AI."""

from .diagnostic import (
    DiagnosticBase,
    DiagnosticOut,
    DiagnosticStatus,
    DTCCode,
    OdometerReading,
    Severity,
)
from .fuel import (
    Currency,
    FuelLogBase,
    FuelLogOut,
    FuelReceiptOCR,
    FuelStats,
    FuelType,
)
from .vehicle import (
    ConditionLabel,
    TradeInBand,
    ValuationOut,
    VehicleBase,
    VehicleCreate,
    VehicleOut,
    VehicleType,
)

__all__ = [
    "DiagnosticBase",
    "DiagnosticOut",
    "DiagnosticStatus",
    "DTCCode",
    "OdometerReading",
    "Severity",
    "Currency",
    "FuelLogBase",
    "FuelLogOut",
    "FuelReceiptOCR",
    "FuelStats",
    "FuelType",
    "ConditionLabel",
    "TradeInBand",
    "ValuationOut",
    "VehicleBase",
    "VehicleCreate",
    "VehicleOut",
    "VehicleType",
]
