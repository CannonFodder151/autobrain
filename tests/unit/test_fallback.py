"""Unit tests for deterministic fallback."""

from ai.app.fallbacks.deterministic import compute_deterministic_score, is_valid_score


def test_fallback_returns_valid_score_empty():
    r = compute_deterministic_score({})
    assert 0 <= r["score"] <= 100
    assert r["method"] == "deterministic_fallback"
    assert isinstance(r["status"], str)


def test_fallback_score_in_range():
    r = compute_deterministic_score({"cpu_usage": 50})
    assert 0 <= r["score"] <= 100


def test_is_valid_score_valid():
    assert is_valid_score(0) is True
    assert is_valid_score(100) is True
    assert is_valid_score(50.5) is True


def test_is_valid_score_invalid():
    assert is_valid_score(-1) is False
    assert is_valid_score(101) is False
    assert is_valid_score("x") is False
    assert is_valid_score(None) is False

    assert is_valid_score(float("inf")) is False
    assert is_valid_score(float("nan")) is False
