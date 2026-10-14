"""AUT-5460: per-client login rate limiting behind Cloudflare (AUT-3858).

Reproduced live 2026-10-04: `POST /api/v1/auth/login` returned 429 on a
FIRST attempt, while a correct password returned 401. Root cause: the
`X-Real-IP` the frontend proxy sends was NOT the visitor.

Not the edge node, as first triaged — the container's immediate TCP
peer. Measured live on hosted (PR #901):

    redis-cli --scan --pattern 'login:fail:*'
      login:fail:ip:172.18.0.3        # 172.18.0.3 = container `npm`

So $remote_addr was the local reverse proxy's own docker-bridge
address, and every visitor on the entire internet shared one
`login:fail:ip:` key (LOGIN_MAX_ATTEMPTS=5, LOGIN_WINDOW_SECONDS=3h):
five failures by anyone locked out every customer for three hours.
Cloudflare's edge ranges alone never match that peer, so trusting only
them left the realip module inert (merged as 08a5fb29).

The fix is nginx-only, deliberately, so the AUT-303 spoof fix stays closed:

- `docker/frontend/nginx.conf` sets `real_ip_header CF-Connecting-IP`
  (forwarded through untouched by the proxy) and trusts BOTH Cloudflare's
  published edge ranges and the docker bridge pool the proxy hops over.
- `client_ip()` still trusts ONLY the proxy-set `X-Real-IP` and otherwise
  the socket peer. `set_real_ip_from` is the trust boundary: a request
  arriving from outside the allowlist is never rewritten from a
  client-supplied `CF-Connecting-IP` / `X-Forwarded-For`.

Run: cd backend && python3 -m pytest tests/test_aut5460_cf_real_ip.py -q
"""

import re

from starlette.requests import Request

from app.services.auth import client_ip

# Cloudflare's published edge ranges (IPv4 + IPv6). If Cloudflare adds a
# range, add it here and to the conf file — the assertions below fail
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
    "198.41.128.0/17",
    "2400:cb00::/32",
    "2606:4700::/32",
    "2803:f800::/32",
    "2405:b500::/32",
    "2405:8100::/32",
    "2a06:98c0::/29",
    "2c0f:f248::/32",
)

# The ONLY non-Cloudflare ranges that may be trusted: the local reverse
# proxy, which is the container's actual immediate peer and reaches it
# over the docker bridge pool (hosted npm 172.18.0.3, EP2 host nginx
# 172.26.0.1). Deliberately explicit so the inverse assertion below can
# pin the trust boundary in both directions — without the bridge pool the
# realip module never fires and the whole-internet shared bucket returns.
PROXY_TRUSTED_RANGES = ("172.16.0.0/12",)

CONFS = (("nginx.conf", "docker/frontend/nginx.conf"),)


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
    """Every Cloudflare edge range must be trusted in the conf.

    173.245.48.0/20 (IPv4) and 2a06:98c0::/29 (IPv6) are asserted
    individually so a partial list is still caught.
    """
    for name, rel in CONFS:
        trusted = _trusted_ranges(_read(rel))
        assert "173.245.48.0/20" in trusted, f"{name}: IPv4 edge range missing"
        assert "2a06:98c0::/29" in trusted, f"{name}: IPv6 edge range missing"
        assert "198.41.128.0/17" in trusted, f"{name}: 15th IPv4 edge range missing"
        missing = [r for r in CF_RANGES if r not in trusted]
        assert not missing, f"{name}: untrusted Cloudflare ranges {missing}"


def test_proxy_peer_pool_is_trusted() -> None:
    """The realip module only fires if the ACTUAL peer is trusted.

    The container's immediate peer is the local reverse proxy on the
    docker bridge, not a Cloudflare edge. Omitting the bridge pool is
    what made the Cloudflare-ranges-only fix (08a5fb29) inert on hosted,
    leaving every visitor sharing one login-failure bucket.
    """
    for name, rel in CONFS:
        trusted = _trusted_ranges(_read(rel))
        missing = [r for r in PROXY_TRUSTED_RANGES if r not in trusted]
        assert not missing, f"{name}: local proxy peer not trusted {missing}"


def test_trusted_set_is_exactly_the_allowlist() -> None:
    """Pin the inverse: the trust boundary is the allowlist, nothing more.

    Without this, a stale list passes CI (that is how 198.41.128.0/17
    shipped) and so does an over-broad edit — `set_real_ip_from
    0.0.0.0/0;` or a bare RFC1918 range would let any client forge
    CF-Connecting-IP, re-opening the AUT-303 bypass at the proxy.
    """
    allowed = set(CF_RANGES) | set(PROXY_TRUSTED_RANGES)
    for name, rel in CONFS:
        trusted = _trusted_ranges(_read(rel))
        extra = trusted - allowed
        assert not extra, f"{name}: trusts ranges outside the allowlist {sorted(extra)}"
        absent = allowed - trusted
        assert not absent, f"{name}: allowlist ranges not trusted {sorted(absent)}"


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


def _directives_only(text: str) -> str:
    """Drop nginx comments so a prose mention is not read as a directive."""
    return re.sub(r"#.*", "", text)


def test_api_proxy_still_forwards_real_remote_addr() -> None:
    """The rewrite only helps if /api forwards the rewritten address.

    nginx.conf sets X-Real-IP (what client_ip() trusts) and overwrites
    X-Forwarded-For with $remote_addr — NOT $proxy_add_x_forwarded_for,
    which would re-attach the client-supplied (spoofable) chain in
    front of the real hop.
    """
    text = _read("docker/frontend/nginx.conf")
    assert "proxy_set_header X-Real-IP $remote_addr;" in text
    directives = _directives_only(text)
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in directives
    assert "$proxy_add_x_forwarded_for" not in directives


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
