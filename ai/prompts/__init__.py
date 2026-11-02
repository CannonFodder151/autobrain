"""Prompt templates for AI features."""

from __future__ import annotations

from typing import Dict


def format_health_score_prompt(metrics: Dict[str, float]) -> str:
    """Render a prompt describing vehicle health metrics."""
    lines = [f"{k}={v}" for k, v in metrics.items()]
    return "Score vehicle health (0-100) given metrics:\n" + "\n".join(lines)