"""JSON helpers shared by backend and AI."""

from __future__ import annotations

import json
from typing import Any


def clean_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from fenced or wrapped model output."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in model response")
    return json.loads(text[start : end + 1])


def normalize_dict(value: Any) -> dict[str, Any]:
    """Recursively convert mapping-like data to a plain dict."""
    if isinstance(value, dict):
        return {str(k): normalize_dict(v) for k, v in value.items()}
    if isinstance(value, list):
        return [normalize_dict(v) for v in value]
    return value
