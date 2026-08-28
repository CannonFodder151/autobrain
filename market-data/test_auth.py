"""Regression tests for /search constant-time auth + rate limiting (AUT-782).

AUT-1326: the per-IP limit keys on socket remote address only (XFF is
spoofable), so IP variation is simulated with distinct TestClient source
addresses instead of X-Forwarded-For headers.

Run: python test_auth.py   (needs: slowapi + httpx installed)
"""

import hmac
import os
import sys

os.environ.setdefault("RATE_LIMIT_IP", "4/minute")
os.environ.setdefault("RATE_LIMIT_KEY", "8/minute")
os.environ.setdefault("API_KEY", "test-key")

sys.path.insert(0, ".")
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


async def _fake_search(query, year):
    return {"source": "carsguide", "listings": []}


main.search_carsguide = _fake_search
main.search_bikesguide = _fake_search

KEY = "test-key"


def _search(ip, key=KEY, query="toyota camry", xff=None):
    client = TestClient(main.app, client=(ip, 12345))
    headers = {}
    if key:
        headers["X-API-Key"] = key
    if xff:
        headers["X-Forwarded-For"] = xff
    return client.post("/search", json={"query": query}, headers=headers)


def _reset_limits():
    # In-memory buckets are shared across tests; start each test clean.
    main.limiter.limiter.storage.reset()


def test_auth_uses_constant_time_compare():
    _reset_limits()
    # The key check must go through hmac.compare_digest, not plain != .
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    hmac.compare_digest = spy
    try:
        assert _search("1.1.1.1", key=KEY).status_code == 200
        assert _search("1.1.1.1", key="wrong-key").status_code == 401
    finally:
        hmac.compare_digest = real
    assert calls, "X-API-Key check did not use hmac.compare_digest"


def test_per_ip_limit():
    _reset_limits()
    # Each IP is allowed RATE_LIMIT_IP (4) searches; the 5th gets 429.
    for _ in range(4):
        r = _search("2.2.2.2")
        assert r.status_code == 200, r.text
    r = _search("2.2.2.2")
    assert r.status_code == 429, r.text
    assert r.headers.get("retry-after"), "429 must carry Retry-After"
    # A different IP shares neither bucket and still works.
    assert _search("3.3.3.3").status_code == 200


def test_xff_does_not_rotate_ip_bucket():
    _reset_limits()
    # AUT-1326: rotating fake X-Forwarded-For values from one source address
    # must NOT evade the per-IP limit.
    for i in range(4):
        r = _search("5.5.5.5", xff=f"10.9.9.{i}")
        assert r.status_code == 200, r.text
    r = _search("5.5.5.5", xff="10.9.9.99")
    assert r.status_code == 429, "XFF rotation bypassed the per-IP limit"


def test_per_key_limit():
    _reset_limits()
    # A single key is allowed RATE_LIMIT_KEY (8) searches even from many IPs.
    main.API_KEY = "key-a"
    for i in range(8):
        r = _search(f"10.0.0.{i}", key="key-a")
        assert r.status_code == 200, r.text
    r = _search("10.0.0.9", key="key-a")
    assert r.status_code == 429, r.text
    # An unrelated key is not rate-limited (auth still rejects the wrong key).
    r = _search("10.0.0.10", key="key-b")
    assert r.status_code == 401, r.text


def test_missing_key_rejected():
    _reset_limits()
    # No key falls into the shared "anon" bucket and is still IP-limited.
    main.API_KEY = "test-key"
    for i in range(4):
        r = _search(f"10.1.0.{i}", key=None)
        assert r.status_code == 401, r.text
    r = _search("10.1.0.99", key=None)
    assert r.status_code == 401, r.text


if __name__ == "__main__":
    test_auth_uses_constant_time_compare()
    test_per_ip_limit()
    test_xff_does_not_rotate_ip_bucket()
    test_per_key_limit()
    test_missing_key_rejected()
    print("all tests passed")
