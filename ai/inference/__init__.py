"""Minimal inference interfaces for AI model execution.

Stubs for future model runners; current gateway still accepts any model object.
"""

from __future__ import annotations

from typing import Any, Protocol


class InferenceModel(Protocol):
    """Protocol for objects that can produce a prediction from metrics."""

    def predict(self, metrics: dict, vehicle_data: dict | None = None) -> Any: ...