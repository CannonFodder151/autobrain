"""Shared schemas package for AutoBrain.

Provides cross-module Pydantic schemas used by both backend and AI.
Importing from shared.schemas avoids duplication between
backend/app/schemas and ai/app/fallbacks.

Available submodules:
- vehicle: VehicleBase, VehicleOut, VehicleCreate, TradeInBand, ValuationOut
- fuel: FuelLogBase, FuelLogOut, FuelStats, FuelReceiptOCR
- diagnostic: DiagnosticBase, DiagnosticOut, DTCCode, OdometerReading
"""

__all__ = ["vehicle", "fuel", "diagnostic"]
