"""AUT-5460: per-client login rate limiting behind Cloudflare (AUT-3858).

Reproduced live 2026-10-04: `POST /api/v1/auth/login` returned 429 on a
FIRST attempt on default, while hosted returned the correct 401. Root cause:
without the realip module, nginx's `$remote_addr` is the Cloudflare edge IP
behind which every visitor on that edge node shares one
`login:fail:ip:<ip>` bucket (LOGIN_MAX_ATTEMPTS=5, LOGIN_WINDOW_SECONDS=3h),
so five failures by anyone locked out every customer on that edge.

The fix is nginx-only, deliberately, so the AUT-303 spoof fix stays closed:

- `docker/frontend/nginx.conf` + `nginx-proxy.conf` gain
  `real_ip_header CF-Connecting-IP` + `set_real_ip_from` for the Cloudflare
  edge ranges, which makes the already-sent `X-Real-IP $remote_addr` carry
  the real visitor to the backend.
- `client_ip()` still trusts ONLY the proxy-set `X-Real-IP` and otherwise
  the socket peer. `set_real_ip_from` is the trust boundary: a request
  arriving from outside a Cloudflare range is never rewritten from a
  client-supplied `CF-Connecting-IP` / `X-Forwarded-For`.

Run: cd backend && python3 -m pytest tests/test_aut5460_cf_real_ip.py -q
"""

import re

from starlette.requests import Request

from app.services.auth import client_ip

# Cloudflare's published edge ranges (IPv4 + IPv6). If Cloudflare adds a
# range, add it here and to both conf files — the assertions below fail
# otherwise, so a stale list cannot silently reintroduce the lockout.
CF_RANGES = (
    "173.245.48.0/20",
    "103.21.244.0/22",
    "103.22.200.0/22",
    "103.31.4.0/22",
    "141.101.64.0/18",
    "108.162.192.0/18",
    "190.93.240.0/20",
    "188.114.96.0/20",
    "197.234.240.0/22",
    "162.158.0.0/15",
    "104.16.0.0/13",
    "104.24.0.0/14",
    "172.64.0.0/13",
    "131.0.72.0/22",
    "2400:cb00::/32",
    "2606:4700::/32",
    "2803:f800::/32",
    "2405:b500::/32",
    "2405:8100::/32",
    "2a06:98c0::/29",
    "2c0f:f248::/32",
)

CONFS = (
    ("nginx.conf", "docker/frontend/nginx.conf"),
    ("nginx-proxy.conf", "docker/frontend/nginx-proxy.conf"),
)


def _read(rel: str) -> str:
    from pathlib import Path

    return (Path(__file__).parents[2] / rel).read_text()


def _trusted_ranges(text: str) -> set[str]:
    return {
        m.group(1).strip()
        for m in re.finditer(r"^\s*set_real_ip_from\s+([^;]+);", text, re.MULTILINE)
    }


def test_both_confs_trust_cloudflare_edge() -> None:
    """Both frontend nginx configs must set real_ip_header CF-Connecting-IP."""
    for name, rel in CONFS:
        text = _read(rel)
        assert "real_ip_header CF-Connecting-IP;" in text, f"{name}: real_ip_header missing"


def test_both_confs_list_every_cloudflare_range() -> None:
    """Every Cloudflare edge range must be trusted in both configs.

    173.245.48.0/20 (IPv4) and 2a06:98c0::/29 (IPv6) are asserted
    individually so a partial list is still caught.
    """
    for name, rel in CONFS:
        trusted = _trusted_ranges(_read(rel))
        assert "173.245.48.0/20" in trusted, f"{name}: IPv4 edge range missing"
        assert "2a06:98c0::/29" in trusted, f"{name}: IPv6 edge range missing"
        missing = [r for r in CF_RANGES if r not in trusted]
        assert not missing, f"{name}: untrusted Cloudflare ranges {missing}"


def test_realip_directives_are_server_level() -> None:
    """real_ip_header must sit in the server block, before the locations.

    A stray copy inside a `location` that does not proxy /api would leave
    $remote_addr rewritten for the SPA only, so the login bucket stays keyed
    on the edge IP.
    """
    for name, rel in CONFS:
        text = _read(rel)
        assert text.index("real_ip_header CF-Connecting-IP;") < text.index("location /api/"), (
            f"{name}: real_ip_header must precede the /api location"
        )


def test_api_proxy_still_forwards_real_remote_addr() -> None:
    """The rewrite only helps if /api forwards the rewritten address.

    nginx.conf sets X-Real-IP (what client_ip() trusts); nginx-proxy.conf
    sets X-Forwarded-For $remote_addr — NOT $proxy_add_x_forwarded_for, which
    would re-attach the client-supplied (spoofable) chain in front of the
    real hop.
    """
    assert "proxy_set_header X-Real-IP $remote_addr;" in _read("docker/frontend/nginx.conf")
    proxy_conf = _read("docker/frontend/nginx-proxy.conf")
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in proxy_conf
    assert "$proxy_add_x_forwarded_for" not in proxy_conf


def _request(headers: dict[str, str] | None = None, peer: str = "203.0.113.50") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/auth/login",
        "query_string": b"",
        "headers": [
            (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
        ],
        "client": (peer, 54321),
    }
    return Request(scope)


def test_client_ip_ignores_client_supplied_xff() -> None:
    """AUT-303 pin: X-Forwarded-For is client-controlled, never trusted.

    Before AUT-303 client_ip() took the first XFF hop, so a rotating forged
    header gave every attempt a fresh rate-limit key. With the header
    ignored, a request that bypasses nginx (or arrives without X-Real-IP)
    buckets on the socket peer.
    """
    req = _request({"X-Forwarded-For": "1.2.3.4"})
    assert client_ip(req) == "203.0.113.50"


def test_client_ip_ignores_client_supplied_cf_header() -> None:
    """The backend must not start trusting CF-Connecting-IP itself.

    nginx's realip module consumes that header (only from Cloudflare
    ranges) and re-emits the result as X-Real-IP. A backend that also read
    CF-Connecting-IP would re-open AUT-303 on any path that skips nginx.
    """
    req = _request({"CF-Connecting-IP": "1.2.3.4"})
    assert client_ip(req) == "203.0.113.50"


def test_client_ip_prefers_proxy_set_x_real_ip() -> None:
    """With the AUT-5460 fix, X-Real-IP is the realip-rewritten visitor."""
    req = _request(
        {"X-Real-IP": "198.51.100.7", "X-Forwarded-For": "1.2.3.4", "CF-Connecting-IP": "1.2.3.4"}
    )
    assert client_ip(req) == "198.51.100.7"


def test_client_ip_falls_back_to_socket_peer() -> None:
    assert client_ip(_request()) == "203.0.113.50"
