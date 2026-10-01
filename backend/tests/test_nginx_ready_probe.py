#!/usr/bin/env python3
"""Self-check for AUT-4532 — /ready must proxy to the backend, not the SPA.

The `location /` SPA fallback answers any unmatched path with index.html
(200 + text/html), so a /ready probe "passed" without ever touching the
backend. These checks pin an exact-match /ready location in nginx.conf.
"""
from pathlib import Path

NGINX_CONF = Path(__file__).parents[2] / "docker" / "frontend" / "nginx.conf"


def test_ready_has_exact_location():
    content = NGINX_CONF.read_text()
    assert "location = /ready {" in content, "no exact /ready location in nginx.conf"
    assert "proxy_pass $backend/health;" in content, "/ready must proxy to the backend"


def test_ready_block_precedes_spa_fallback():
    content = NGINX_CONF.read_text()
    assert content.index("location = /ready {") < content.rindex("try_files $uri $uri/ /index.html;")


if __name__ == "__main__":
    test_ready_has_exact_location()
    test_ready_block_precedes_spa_fallback()
    print("✓ All AUT-4532 /ready proxy self-checks passed")
