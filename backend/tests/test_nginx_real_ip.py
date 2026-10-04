#!/usr/bin/env python3
"""Self-check for AUT-5460 — nginx must forward the REAL client IP.

Public traffic arrives at the frontend via the host npm proxy, so
`$remote_addr` is the proxy's address for every visitor. Without the
real-IP block the backend's login rate limiter keys one bucket for the
whole internet (`login:fail:ip:172.18.0.3` on hosted): five failures
from anyone lock every user out for three hours (AUT-3858).

These checks pin the block so it cannot be dropped, and so it cannot be
widened into something a public client could spoof.
"""
import ipaddress
import re
from pathlib import Path

NGINX_CONF = Path(__file__).parents[2] / "docker" / "frontend" / "nginx.conf"

TRUST_RE = re.compile(r"^\s*set_real_ip_from\s+(\S+);", re.MULTILINE)


def _conf() -> str:
    return NGINX_CONF.read_text()


def test_real_ip_block_present():
    content = _conf()
    assert "real_ip_header CF-Connecting-IP;" in content, (
        "nginx.conf must restore the client IP from CF-Connecting-IP "
        "(AUT-5460); without it the login rate limiter keys the proxy IP"
    )
    assert TRUST_RE.search(content), "nginx.conf has no set_real_ip_from"


def test_trusted_proxies_are_private_only():
    """A public range in the trust list would let any client spoof CF-Connecting-IP."""
    trusted = TRUST_RE.findall(_conf())
    assert trusted, "no trusted proxies configured"
    for cidr in trusted:
        net = ipaddress.ip_network(cidr, strict=False)
        assert net.is_private or net.is_loopback, (
            f"{cidr} is publicly routable — any client could spoof its IP"
        )


def test_real_ip_block_precedes_proxy_headers():
    """Real-IP rewriting must be declared before any X-Real-IP is sent upstream."""
    content = _conf()
    assert content.index("real_ip_header CF-Connecting-IP;") < content.index(
        "proxy_set_header X-Real-IP $remote_addr;"
    ), "X-Real-IP is forwarded before the real-IP block"


def test_backend_gets_corrected_address_not_a_client_supplied_header():
    """X-Real-IP must carry $remote_addr, never a client-supplied header."""
    content = _conf()
    for forbidden in (
        "proxy_set_header X-Real-IP $http_x_real_ip;",
        "proxy_set_header X-Real-IP $http_cf_connecting_ip;",
    ):
        assert forbidden not in content, (
            f"{forbidden} trusts a client-supplied header (AUT-303 bypass)"
        )


if __name__ == "__main__":
    test_real_ip_block_present()
    test_trusted_proxies_are_private_only()
    test_real_ip_block_precedes_proxy_headers()
    test_backend_gets_corrected_address_not_a_client_supplied_header()
    print("✓ All AUT-5460 nginx real-IP self-checks passed")
