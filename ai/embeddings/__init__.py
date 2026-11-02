"""Embedding generation utilities for AI features."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class EmbeddingGenerator:
    """Thin wrapper around an embedding model."""

    def __init__(self, model: Optional[Any] = None) -> None:
        self._model = model

    def embed(self, text: str) -> List[float]:
        if self._model is None:
            return []
        try:
            return list(self._model.embed(text))
        except Exception:
            return []