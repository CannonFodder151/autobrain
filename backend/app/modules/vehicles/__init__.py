"""Vehicles domain module.

This module owns all vehicle-related code, organized by layer:
- models: SQLAlchemy models (Vehicle, VehicleEvent, PowertrainType)
- schemas: Pydantic schemas for API contracts
- services: Business logic (ownership, rego lookup, odometer sync, timeline)
- api: FastAPI routes

Layers are imported explicitly by their full path
(``app.modules.vehicles.models`` and so on). This package deliberately does not
re-export them, because ``app.models.vehicle`` re-exports *from* here for
backwards compatibility: eagerly importing the layers here would make that
re-export circular.
"""
