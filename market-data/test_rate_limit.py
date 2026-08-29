"""Regression tests for market-data /search + /sca-parts IP rate-limiting.

AUT-1741: an untrusted caller must NOT be able to rotate per-IP rate-limit
buckets by spoofing X-Forwarded-For. This mirrors the rego-lookup-api pattern:
the socket peer (not a caller-controlled XFF header) keys the IP bucket unless
the peer is itself an allowlisted trusted proxy, in which case the rightmost
non-trusted XFF hop is the real client.

The test sizes its loops from the *active* limit values bound at import time,
so it is robust whether `main` is imported here first or by a sibling test that
left the env at defaults (RATE_LIMIT_{IP,KEY} are captured by the decorators at
import; TRUSTED_NETWORKS / API_KEY are read per-request and are reset below).

Run:
    python3 test_rate_limit.py        (runnable, reports "all tests passed")
    python3 -m pytest test_rate_limit.py -v
(needs: slowapi + fastapi + httpx installed)
"""

import ipaddress
import os
import sys

os.environ.setdefault("RATE_LIMIT_IP", "4/minute")
os.environ.setdefault("RATE_LIMIT_KEY", "6/minute")
os.environ.setdefault("API_KEY", "test-key")
# Simulate deployment behind an allowlisted reverse proxy: the TestClient
# connects from 203.0.113.7, the only trusted proxy.
os.environ.setdefault("TRUSTED_PROXIES", "203.0.113.7")

sys.path.insert(0, ".")
import main  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

try:
    import pytest  # noqa: E402
except ModuleNotFoundError:
    pytest = None


async def _fake_search(query, year=None):
    return {"source": "carsguide", "listings": [], "note": None}


async def _fake_sca(**kwargs):
    return {"source": "supercheap", "vehicle": None, "parts": [], "categories": [], "note": None}


main.search_carsguide = _fake_search
main.search_bikesguide = _fake_search
main.search_sca = _fake_sca

client = TestClient(main.app, client=("203.0.113.7", 1500))
KEY = "test-key"


def _limit_count(val):
    """'4/minute' -> 4 (the per-window request ceiling, inclusive)."""
    return int(str(val).split("/")[0])


def _reset():
    main.API_KEY = "test-key"
    main.TRUSTED_NETWORKS = [ipaddress.ip_network("203.0.113.7", strict=False)]
    main.limiter.reset()


if pytest is not None:
    @pytest.fixture(autouse=True)
    def _isolate():
        _reset()
        yield
        main.limiter.reset()


def _search(ip, key=KEY, vehicle_type="car"):
    headers = {}
    if key:
        headers["X-API-Key"] = key
    if ip:
        headers["X-Forwarded-For"] = ip
    return client.post("/search", json={"query": "toyota corolla", "vehicle_type": vehicle_type}, headers=headers)


def _sca(ip, key=KEY):
    headers = {}
    if key:
        headers["X-API-Key"] = key
    if ip:
        headers["X-Forwarded-For"] = ip
    return client.post("/sca-parts", json={"make": "toyota"}, headers=headers)


def test_per_ip_limit():
    # N calls from the same real IP -> 200; the (N+1)th -> 429 with Retry-After,
    # where N = RATE_LIMIT_IP. A distinct IP keeps its own fresh bucket.
    n = _limit_count(main.RATE_LIMIT_IP)
    for _ in range(n):
        assert _search("1.2.3.4").status_code == 200
    r = _search("1.2.3.4")
    assert r.status_code == 429, r.text
    assert r.headers.get("retry-after"), "429 must carry Retry-After"
    assert _search("5.6.7.8").status_code == 200


def test_per_key_limit():
    # A single key is allowed RATE_LIMIT_KEY calls even from many IPs; the next
    # call with that key is 429. A wrong key is rejected by auth (401).
    main.API_KEY = "key-a"
    nkey = _limit_count(main.RATE_LIMIT_KEY)
    for i in range(nkey):
        assert _search(f"10.0.0.{i}", key="key-a").status_code == 200
    assert _search("10.0.0.99", key="key-a").status_code == 429
    assert _search("10.0.0.100", key="key-b").status_code == 401


def test_xff_ignored_without_trusted_proxy():
    # AUT-1741 core: with no trusted proxy configured, spoofed XFF must NOT
    # mint new per-IP buckets — every spoofed request keys off the socket peer.
    main.API_KEY = "key-spoof"
    saved = list(main.TRUSTED_NETWORKS)
    main.TRUSTED_NETWORKS = []
    try:
        n = _limit_count(main.RATE_LIMIT_IP)
        for i in range(n):
            assert _search(f"10.9.9.{i}", key="key-spoof").status_code == 200
        # Same socket peer, (n+1)th spoofed request -> IP bucket exhausted -> 429.
        assert _search("10.9.9.42", key="key-spoof").status_code == 429
    finally:
        main.TRUSTED_NETWORKS = saved


def test_xff_rightmost_untrusted_hop_wins():
    # Behind a trusted proxy, the rightmost non-trusted XFF hop is the real
    # client. Rotating spoofed LEADING entries must NOT change the bucket.
    main.API_KEY = "key-chain"
    n = _limit_count(main.RATE_LIMIT_IP)
    for i in range(n):
        assert _search(f"spoof{i}.example, 10.2.0.7", key="key-chain").status_code == 200
    # Same real client (rightmost hop), (n+1)th call -> IP bucket exhausted -> 429.
    assert _search("spoofXYZ.example, 10.2.0.7", key="key-chain").status_code == 429
    # A different real client gets its own bucket -> 200.
    assert _search("10.2.0.8", key="key-chain").status_code == 200


def test_anon_uses_own_bucket():
    # No key falls into the shared "anon" key bucket and is still IP-limited;
    # auth rejects it with 401 before the scrape runs.
    main.API_KEY = "test-key"
    n = _limit_count(main.RATE_LIMIT_IP)
    for i in range(n):
        assert _search(f"10.1.0.{i}", key=None).status_code == 401
    assert _search("10.1.0.99", key=None).status_code == 401


def test_sca_parts_ip_limit():
    main.API_KEY = "sca-key"
    n = _limit_count(main.RATE_LIMIT_IP)
    for _ in range(n):
        assert _sca("1.2.3.4", key="sca-key").status_code == 200
    assert _sca("1.2.3.4", key="sca-key").status_code == 429
    # Distinct real IP -> own bucket -> 200.
    assert _sca("5.6.7.8", key="sca-key").status_code == 200


if __name__ == "__main__":
    for fn in (
        test_per_ip_limit,
        test_per_key_limit,
        test_xff_ignored_without_trusted_proxy,
        test_xff_rightmost_untrusted_hop_wins,
        test_anon_uses_own_bucket,
        test_sca_parts_ip_limit,
    ):
        _reset()
        fn()
        print(f"ok {fn.__name__}")
    print("all tests passed")
