"""AUT-4120: query-embedding Redis cache (TTL 1h) in vector_search.py.

Covers the acceptance criteria:
- generate_embedding checks Redis first
- a cache hit returns the stored vector with NO 9Router call
- a cache miss calls 9Router, stores the vector, and returns it
- non-query entity types never touch the cache
- a Redis outage fails open (the 9Router path still runs)
"""

import os

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test-user:test-password@postgres:5432/autobrain")
os.environ.setdefault("SECRET_KEY", "test-secret")

import json  # noqa: E402
from unittest.mock import AsyncMock, patch  # noqa: E402

import pytest  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.services import vector_search  # noqa: E402
from app.services.vector_search import (  # noqa: E402
    _normalize_query,
    _query_cache_key,
    generate_embedding,
)

_DIM = settings.EMBEDDING_DIMENSION
_VECTOR = [0.25] * _DIM
_QUERY = "brake squeal when turning"


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------

def test_normalize_collapses_case_and_whitespace() -> None:
    assert _normalize_query("  Brake   Squeal\nWhen  Turning ") == "brake squeal when turning"


def test_cache_key_is_stable_for_equivalent_queries() -> None:
    a = _query_cache_key(_normalize_query("Brake  Squeal"))
    b = _query_cache_key(_normalize_query("brake squeal"))
    assert a == b
    assert a.startswith("embedding:query:")


def test_cache_key_differs_for_different_queries() -> None:
    assert _query_cache_key(_normalize_query("brake squeal")) != _query_cache_key(
        _normalize_query("oil change")
    )


# ---------------------------------------------------------------------------
# generate_embedding cache behaviour
# ---------------------------------------------------------------------------

def _fake_redis(store: dict) -> AsyncMock:
    """Minimal async Redis stub: get/setex over a plain dict."""
    r = AsyncMock()
    r.get = AsyncMock(side_effect=lambda key: store.get(key))
    r.setex = AsyncMock(side_effect=lambda key, ttl, value: store.__setitem__(key, value))
    r.aclose = AsyncMock(return_value=None)
    return r


@pytest.mark.asyncio
async def test_cache_hit_skips_9router_call() -> None:
    store: dict = {}
    cached = _query_cache_key(_normalize_query(_QUERY))
    store[cached] = json.dumps(_VECTOR)

    api = AsyncMock(return_value=None)  # any 9Router call fails the test
    with (
        patch.object(vector_search, "_redis_client", return_value=_fake_redis(store)),
        patch.object(vector_search, "_call_embedding_api", new=api),
    ):
        result = await generate_embedding("query", {"symptoms": _QUERY})

    assert result == _VECTOR
    api.assert_not_called()


@pytest.mark.asyncio
async def test_cache_miss_calls_9router_then_stores() -> None:
    store: dict = {}
    api = AsyncMock(return_value=list(_VECTOR))
    with (
        patch.object(vector_search, "_redis_client", return_value=_fake_redis(store)),
        patch.object(vector_search, "_call_embedding_api", new=api),
    ):
        result = await generate_embedding("query", {"symptoms": _QUERY})

    assert result == _VECTOR
    api.assert_awaited_once()
    key = _query_cache_key(_normalize_query(_QUERY))
    assert json.loads(store[key]) == _VECTOR


@pytest.mark.asyncio
async def test_second_identical_query_is_served_from_cache() -> None:
    store: dict = {}
    api = AsyncMock(return_value=list(_VECTOR))
    with (
        patch.object(vector_search, "_redis_client", return_value=_fake_redis(store)),
        patch.object(vector_search, "_call_embedding_api", new=api),
    ):
        first = await generate_embedding("query", {"symptoms": _QUERY})
        # Same text, different case/whitespace — must hit the same cache entry.
        second = await generate_embedding("query", {"symptoms": f"  {_QUERY.upper()} "})

    assert first == second == _VECTOR
    api.assert_awaited_once()  # second call served from cache


@pytest.mark.asyncio
async def test_cache_ttl_is_one_hour() -> None:
    store: dict = {}
    api = AsyncMock(return_value=list(_VECTOR))
    r = _fake_redis(store)
    with (
        patch.object(vector_search, "_redis_client", return_value=r),
        patch.object(vector_search, "_call_embedding_api", new=api),
    ):
        await generate_embedding("query", {"symptoms": _QUERY})

    r.setex.assert_awaited_once()
    assert r.setex.await_args.args[1] == 3600


@pytest.mark.asyncio
async def test_non_query_entity_never_uses_cache() -> None:
    store: dict = {}
    api = AsyncMock(return_value=list(_VECTOR))
    r = _fake_redis(store)
    with (
        patch.object(vector_search, "_redis_client", return_value=r),
        patch.object(vector_search, "_call_embedding_api", new=api),
    ):
        await generate_embedding("service", {"description": "oil change"})

    api.assert_awaited_once()
    r.get.assert_not_called()
    r.setex.assert_not_called()


@pytest.mark.asyncio
async def test_redis_outage_fails_open_and_still_embeds() -> None:
    broken = AsyncMock()
    broken.get = AsyncMock(side_effect=ConnectionError("redis down"))
    broken.setex = AsyncMock(side_effect=ConnectionError("redis down"))
    broken.aclose = AsyncMock(return_value=None)
    api = AsyncMock(return_value=list(_VECTOR))

    with (
        patch.object(vector_search, "_redis_client", return_value=broken),
        patch.object(vector_search, "_call_embedding_api", new=api),
    ):
        result = await generate_embedding("query", {"symptoms": _QUERY})

    assert result == _VECTOR  # cache failure must not break search
    api.assert_awaited_once()


@pytest.mark.asyncio
async def test_cached_vector_is_dimension_validated_on_read() -> None:
    """A poisoned cache entry must not reach SQL as a wrong-dimension vector."""
    store: dict = {
        _query_cache_key(_normalize_query(_QUERY)): json.dumps([0.1] * (_DIM - 1))
    }
    api = AsyncMock(return_value=list(_VECTOR))
    with (
        patch.object(vector_search, "_redis_client", return_value=_fake_redis(store)),
        patch.object(vector_search, "_call_embedding_api", new=api),
    ):
        result = await generate_embedding("query", {"symptoms": _QUERY})

    # Stale/corrupt entry is rejected; the router path re-derives the vector.
    assert result == _VECTOR
    assert len(result) == _DIM
    api.assert_awaited_once()
