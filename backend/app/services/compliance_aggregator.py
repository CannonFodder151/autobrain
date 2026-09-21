"""Compliance results aggregation — deterministic, no AI.

Aggregates per-modification compliance results into an overall summary
score and pass/fail breakdown for a precheck session.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def aggregate_compliance_results(
    results: list[Any],
) -> dict:
    """Aggregate compliance results for a precheck or vehicle.

    Each result item should have: name, category, status, adr_references,
    vsb_references, notes, created_at.

    Returns an aggregated summary with overall score, counts, and details.
    """
    if not results:
        return {
            "overall_score": 0.0,
            "total_mods": 0,
            "passed": 0,
            "failed": 0,
            "conditional": 0,
            "pending": 0,
            "requires_engineer_review": False,
            "summary": "No modifications evaluated.",
            "results": [],
        }

    counts = {"pass": 0, "fail": 0, "conditional": 0, "pending": 0, "na": 0}
    requires_review = False
    result_list: list[dict] = []

    for r in results:
        status = getattr(r, "status", "pending")
        status_val = status.value if hasattr(status, "value") else str(status)
        if status_val in counts:
            counts[status_val] += 1
        else:
            counts["pending"] += 1

        if getattr(r, "status", None) in ("fail",) or status_val == "fail":
            requires_review = True
        if getattr(r, "requires_engineer_review", False):
            requires_review = True

        adr_refs = getattr(r, "adr_references", None)
        if adr_refs is None:
            adr_refs = []
        elif isinstance(adr_refs, str):
            import json
            try:
                adr_refs = json.loads(adr_refs)
            except (json.JSONDecodeError, TypeError):
                adr_refs = []
        if not isinstance(adr_refs, list):
            adr_refs = []

        vsb_refs = getattr(r, "vsb_references", None)
        if vsb_refs is None:
            vsb_refs = []
        elif isinstance(vsb_refs, str):
            import json
            try:
                vsb_refs = json.loads(vsb_refs)
            except (json.JSONDecodeError, TypeError):
                vsb_refs = []
        if not isinstance(vsb_refs, list):
            vsb_refs = []

        result_list.append({
            "name": getattr(r, "modification_name", "Unknown"),
            "category": getattr(r, "category", "unknown"),
            "status": status_val,
            "adr_references": adr_refs,
            "vsb_references": vsb_refs,
            "notes": getattr(r, "notes", None),
            "conditional_details": getattr(r, "conditional_details", None),
            "created_at": _format_datetime(getattr(r, "created_at", None)),
        })

    total = len(results)
    score = (counts["pass"] / total * 100) if total > 0 else 0.0
    # Conditional counts partial credit: 50%
    score += (counts["conditional"] * 50.0 / total) if total > 0 else 0.0

    if counts["fail"] > 0:
        summary = f"{counts['fail']} modification(s) non-compliant — engineer review required."
    elif counts["conditional"] > 0:
        summary = f"{counts['conditional']} modification(s) conditionally compliant — review and certification needed."
    elif counts["pending"] > 0:
        summary = f"{counts['pending']} modification(s) pending evaluation."
    elif total > 0:
        summary = f"All {total} modification(s) compliant."
    else:
        summary = "No modifications evaluated."

    return {
        "overall_score": round(score, 1),
        "total_mods": total,
        "passed": counts["pass"],
        "failed": counts["fail"],
        "conditional": counts["conditional"],
        "pending": counts["pending"],
        "requires_engineer_review": requires_review,
        "summary": summary,
        "results": result_list,
    }


def _format_datetime(dt: Any) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        return dt.isoformat()
    return str(dt)
