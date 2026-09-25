"""Modifications module contract.

This module defines the public interface for vehicle modification operations.
Actual implementations live in:
- app.services.modification_checklist (deterministic checklist generation)
- app.services.compliance_aggregator (compliance aggregation)
- app.modules.ai_client (AI mod_impact via AI gateway)
- app.models.mod (Modification model)
- app.schemas.mod (Mod schemas)
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.mod import Modification
    from app.schemas.mod import ModCreate, ModUpdate, ModOut, ModImpactRequest, ModImpactResponse

__all__ = [
    "generate_modification_checklist",
    "aggregate_compliance",
    "mod_impact",
    "Modification",
    "ModCreate",
    "ModUpdate",
    "ModOut",
    "ModImpactRequest",
    "ModImpactResponse",
]


def __getattr__(name: str):
    if name == "generate_modification_checklist":
        from app.services.modification_checklist import generate_modification_checklist
        globals()["generate_modification_checklist"] = generate_modification_checklist
        return generate_modification_checklist
    if name == "aggregate_compliance":
        from app.services.compliance_aggregator import aggregate_compliance
        globals()["aggregate_compliance"] = aggregate_compliance
        return aggregate_compliance
    if name == "mod_impact":
        from app.modules.ai_client import mod_impact
        globals()["mod_impact"] = mod_impact
        return mod_impact
    if name == "Modification":
        from app.models.mod import Modification
        globals()["Modification"] = Modification
        return Modification
    if name in {"ModCreate", "ModUpdate", "ModOut", "ModImpactRequest", "ModImpactResponse"}:
        from app.schemas.mod import ModCreate, ModUpdate, ModOut, ModImpactRequest, ModImpactResponse
        globals().update({
            "ModCreate": ModCreate,
            "ModUpdate": ModUpdate,
            "ModOut": ModOut,
            "ModImpactRequest": ModImpactRequest,
            "ModImpactResponse": ModImpactResponse,
        })
        return globals()[name]
    raise AttributeError(f"module 'app.modules.modifications' has no attribute '{name}'")