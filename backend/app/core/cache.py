"""In-process TTL cache utilities.

Simple thread-unsafe cache with time-to-live and max entries. Suitable for
single-process FastAPI workers where cache restart-eviction is acceptable.
"""

import json
import time
from typing import Any, TypeVar

T = TypeVar("T")


class TTLCache:
    """Fixed-window TTL cache with LRU-style eviction on overflow."""

    __slots__ = ("_store", "_ttl_seconds", "_max_entries")

    def __init__(self, ttl_seconds: int, max_entries: int = 1024) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries

    def _now(self) -> float:
        return time.time()

    def _make_key(self, *parts: Any) -> str:
        """Create a stable cache key from parts."""
        canonical = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
        return canonical

    def get(self, key: str) -> T | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < self._now():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: T) -> None:
        if len(self._store) >= self._max_entries:
            cutoff = self._now()
            stale = [k for k, (exp, _) in self._store.items() if exp < cutoff]
            for k in stale[: max(1, len(self._store) - self._max_entries + 1)]:
                self._store.pop(k, None)
            if len(self._store) >= self._max_entries:
                for k in list(self._store.keys())[: len(self._store) - self._max_entries + 1]:
                    self._store.pop(k, None)
        self._store[key] = (self._now() + self._ttl_seconds, value)

    def clear(self) -> None:
        self._store.clear()


# Pre-configured caches used by the AI gateway client.
# 24h TTL matches the advisor/car-check cache in ai_client.py.
advisor_cache = TTLCache(ttl_seconds=24 * 60 * 60, max_entries=1024)
car_check_cache = TTLCache(ttl_seconds=24 * 60 * 60, max_entries=1024)