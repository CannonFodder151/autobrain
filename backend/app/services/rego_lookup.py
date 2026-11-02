"""Australian rego lookup with deterministic fallback."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RegoInfo:
    rego: str
    state: str
    vin: Optional[str] = None
    body: Optional[str] = None
    colour: Optional[str] = None
    status: str = "unknown"
    make: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    errors: List[str] = field(default_factory=list)


def lookup_rego(rego: str, state: str = "NSW") -> RegoInfo:
    rego = (rego or "").strip().upper()
    if not rego:
        return RegoInfo(rego=rego, state=state, errors=["rego required"], status="invalid")
    # Deterministic stub data; real feed would replace this.
    if rego.startswith("ABC"):
        return RegoInfo(rego=rego, state=state, vin="MR0ABC1234567890", body="Sedan", colour="White",
                        status="registered", make="Toyota", model="Corolla", year=2019)
    if rego.startswith("XYZ"):
        return RegoInfo(rego=rego, state=state, vin="1FTXYZ9876543210", body="Ute", colour="Blue",
                        status="expired", make="Ford", model="Ranger", year=2018)
    return RegoInfo(rego=rego, state=state, vin=None, body=None, colour=None, status="not_found",
                    errors=["no record found"])
