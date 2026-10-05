#!/usr/bin/env python3
"""Self-check for AUT-5623: /ai/ upstream must re-resolve at request time.

The frontend proxies /ai/ to the AI gateway on :8001. If `proxy_pass`
carries a LITERAL upstream (e.g. `proxy_pass http://ai:8001/`), nginx
resolves the name once at startup and caches it for the process
lifetime, so any AI-gateway container recreate (new IP) turns every
/ai/* route into a 502. The AUT-373 fix for /api/ uses `set` + a
VARIABLE `proxy_pass` to force request-time re-resolution; /ai/ must
do the same.

Also asserts the topology contract that makes `ai:8001` correct on
every tier: Demo/Default run a dedicated `ai` service, while
hosted/prod/dev run the gateway as an `ai_app.main:app` co-process on
:8001 inside `backend`, which therefore needs an `ai` network alias.
"""
from pathlib import Path

REPO = Path(__file__).parents[2]
NGINX_CONF = REPO / "docker" / "frontend" / "nginx.conf"


def _strip_comments(conf: str) -> str:
    """Drop whole-line comments so prose quoting a bad form cannot fail a test."""
    return "\n".join(
        line for line in conf.splitlines() if not line.strip().startswith("#")
    )


def _ai_block(conf: str) -> str:
    conf = _strip_comments(conf)
    start = conf.index("location /ai/")
    end = conf.index("\n    }", start)
    return conf[start:end]


def test_ai_upstream_uses_variable_not_literal():
    """The /ai/ proxy_pass must go through a variable, not a literal host."""
    block = _ai_block(NGINX_CONF.read_text())
    # The literal form is the bug: resolved once at startup, stale forever.
    assert "proxy_pass http://ai:8001" not in block, (
        "/ai/ uses a literal upstream; it will not re-resolve after a "
        "gateway recreate (AUT-5623)"
    )
    assert "set $ai http://ai:8001;" in block
    assert "proxy_pass $ai/;" in block


def test_ai_prefix_strip_preserved():
    """The trailing slash keeps /ai/ stripped before it reaches the gateway.

    The gateway serves /health and /v1/{module} with no /ai prefix, so
    /ai/health must arrive as /health.
    """
    block = _ai_block(NGINX_CONF.read_text())
    assert "proxy_pass $ai/;" in block, "trailing slash required for /ai/ strip"


def test_gateway_host_is_resolvable_on_every_tier():
    """`ai` must resolve on each tier, and only where it is a co-process.

    On Demo/Default `ai` is a real service (so it resolves by service
    name). On hosted/prod/dev the gateway is an ai_app co-process inside
    `backend`, so `backend` must carry an `ai` network alias.
    """
    import yaml

    tiers = {
        "docker-compose.yml": "co-process",
        "docker-compose.hosted.yml": "co-process",
        "docker-compose.prod.yml": "co-process",
        "docker-compose.demo.yml": "dedicated",
        "docker-compose.default.yml": "dedicated",
    }
    for path, kind in tiers.items():
        doc = yaml.safe_load((REPO / path).read_text())
        services = doc["services"]
        backend = services.get("backend", {})
        nets = backend.get("networks", {}).get("default", {})
        aliases = nets.get("aliases", []) if isinstance(nets, dict) else []
        has_ai_service = "ai" in services

        if kind == "dedicated":
            # Gateway is a separate `ai` service: it resolves by name, and
            # `backend` must NOT also claim the `ai` alias (DNS conflict).
            assert has_ai_service, f"{path}: dedicated gateway missing `ai` service"
            assert "ai" not in aliases, (
                f"{path}: backend claims alias `ai` while a real `ai` service "
                "exists — ambiguous DNS (AUT-5623)"
            )
        else:
            # Gateway is the ai_app co-process inside `backend`: `ai` must be
            # a network alias on `backend` so the frontend can reach it.
            assert not has_ai_service, f"{path}: unexpected separate `ai` service"
            assert "ai" in aliases, (
                f"{path}: gateway is a co-process in `backend` but `backend` "
                "has no `ai` network alias — the frontend's /ai/ will fail "
                "to resolve (AUT-5623)"
            )


if __name__ == "__main__":
    test_ai_upstream_uses_variable_not_literal()
    test_ai_prefix_strip_preserved()
    test_gateway_host_is_resolvable_on_every_tier()
    print("All AUT-5623 /ai/ resolver self-checks passed")
