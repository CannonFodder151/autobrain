"""Deterministic resale estimate with fallback."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ResaleEstimate:
    make: str
    model: str
    year: int
    mileage: int
    estimated_value: float
    trade_in: float
    depreciation_rate: float
    notes: str = ""

def estimate_resale(make: str, model: str, year: int, mileage: int, current_value: Optional[float] = None) -> ResaleEstimate:
    base = current_value if current_value is not None else 20000.0
    rate = 0.05 if mileage < 50000 else 0.08
    depreciation = base * rate
    trade_in = round(base - depreciation * 0.3, 2)
    return ResaleEstimate(make=make, model=model, year=year, mileage=mileage,
                          estimated_value=round(base, 2), trade_in=trade_in,
                          depreciation_rate=rate, notes="Deterministic estimate; market data optional.")
