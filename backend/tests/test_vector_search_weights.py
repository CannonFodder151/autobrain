"""Tests for vector search weight tuning (AUT-3911)."""

import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost/test"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["ADMIN_API_KEY"] = "test-admin-key-0123456789-0123456789"

import json

import pytest

from app.core.config import settings
from app.services.search import _resolve_vector_weights, ENTITY_TYPES, _DEFAULT_VECTOR_WEIGHTS


def test_default_vector_weights_match_expected_keys() -> None:
    """All known entity types have a default weight."""
    assert set(_DEFAULT_VECTOR_WEIGHTS.keys()) == set(ENTITY_TYPES)
    for weight in _DEFAULT_VECTOR_WEIGHTS.values():
        assert weight == 1.0


def test_resolve_vector_weights_returns_defaults_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """When settings.VECTOR_SEARCH_WEIGHTS is empty, defaults are returned."""
    monkeypatch.setattr(settings, "VECTOR_SEARCH_WEIGHTS", {})
    weights = _resolve_vector_weights()
    assert weights == _DEFAULT_VECTOR_WEIGHTS


def test_resolve_vector_weights_uses_settings_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Custom weights from settings are returned."""
    custom = {"diagnostic": 1.5, "service": 0.8, "modification": 1.2, "receipt": 0.6, "issue": 1.1}
    monkeypatch.setattr(settings, "VECTOR_SEARCH_WEIGHTS", custom)
    weights = _resolve_vector_weights()
    assert weights == custom


def test_resolve_vector_weights_fills_missing_with_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing entity types in settings fall back to default weight 1.0."""
    partial = {"diagnostic": 1.5, "service": 0.8}  # missing modification, receipt, issue
    monkeypatch.setattr(settings, "VECTOR_SEARCH_WEIGHTS", partial)
    weights = _resolve_vector_weights()
    assert weights["diagnostic"] == 1.5
    assert weights["service"] == 0.8
    assert weights["modification"] == 1.0
    assert weights["receipt"] == 1.0
    assert weights["issue"] == 1.0


def test_settings_vector_search_weights_default_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """VECTOR_SEARCH_WEIGHTS is parsed from JSON env var."""
    env_json = '{"diagnostic":1.2,"service":0.9,"modification":1.1,"receipt":0.7,"issue":1.0}'
    monkeypatch.setenv("VECTOR_SEARCH_WEIGHTS", env_json)
    # Re-create settings to pick up the env var
    from app.core.config import Settings

    s = Settings(_env_file=None)
    assert s.VECTOR_SEARCH_WEIGHTS == json.loads(env_json)


def test_settings_vector_search_similarity_threshold_default_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """VECTOR_SEARCH_SIMILARITY_THRESHOLD is parsed from env var."""
    monkeypatch.setenv("VECTOR_SEARCH_SIMILARITY_THRESHOLD", "0.85")
    from app.core.config import Settings

    s = Settings(_env_file=None)
    assert s.VECTOR_SEARCH_SIMILARITY_THRESHOLD == 0.85


def test_settings_vector_search_keyword_weight_default_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """VECTOR_SEARCH_KEYWORD_WEIGHT is parsed from env var."""
    monkeypatch.setenv("VECTOR_SEARCH_KEYWORD_WEIGHT", "0.3")
    from app.core.config import Settings

    s = Settings(_env_file=None)
    assert s.VECTOR_SEARCH_KEYWORD_WEIGHT == 0.3


def test_default_settings_values() -> None:
    """Default values in Settings class are correct."""
    assert settings.VECTOR_SEARCH_SIMILARITY_THRESHOLD == 0.75
    assert settings.VECTOR_SEARCH_KEYWORD_WEIGHT == 0.5
    assert settings.VECTOR_SEARCH_WEIGHTS == _DEFAULT_VECTOR_WEIGHTS