"""Regression tests for /search constant-time auth + rate limiting (AUT-782).

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
client = TestClient(main.app)

KEY = "test-key"


def _search(ip, key=KEY, query="toyota camry"):
    headers = {}
    if key:
        headers["X-API-Key"] = key
    if ip:
        headers["X-Forwarded-For"] = ip
    return client.post("/search", json={"query": query}, headers=headers)


def test_auth_uses_constant_time_compare():
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
    # Each IP is allowed RATE_LIMIT_IP (4) searches; the 5th gets 429.
    for _ in range(4):
        r = _search("2.2.2.2")
        assert r.status_code == 200, r.text
    r = _search("2.2.2.2")
    assert r.status_code == 429, r.text
    assert r.headers.get("retry-after"), "429 must carry Retry-After"
    # A different IP shares neither bucket and still works.
    assert _search("3.3.3.3").status_code == 200


def test_per_key_limit():
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
    test_per_key_limit()
    test_missing_key_rejected()
    print("all tests passed")
