#!/usr/bin/env python3
"""AUT-4503: invariants for the standalone EP2 9Router stack.

The EP2 9Router (10.0.3.17:20128) is its own Portainer stack, not part of
docker-compose.hosted.yml, so the AUT-1533 hosted check does not cover it.
Keeping it in a separate file leaves the pre-existing hosted check untouched.

Run: python3 scripts/check-9router-stack.py
No docker daemon needed.
"""
import sys

import yaml

COMPOSE = "docker-compose.9router.yml"


def main():
    with open(COMPOSE) as f:
        svc = yaml.safe_load(f)["services"]["9router"]

    # Digest pin (AUT-1533): the loose container ran the floating `:latest` tag.
    assert "@sha256:" in svc["image"], f"9router not digest-pinned: {svc['image']}"
    # Every LAN stack points AI_ROUTER_URL at http://10.0.3.17:20128/v1, so the
    # published port must stay on 0.0.0.0.
    ports = [str(p) for p in svc["ports"]]
    assert any("0.0.0.0:20128:20128" in p for p in ports), f"9router port map wrong: {ports}"
    # The data bind is the pre-existing provider/API-key/catalog/DB directory.
    vols = [str(v) for v in svc["volumes"]]
    assert any("/home/administrator/9Router:/app/data" in v for v in vols), \
        f"9router data bind changed: {vols}"
    # Portainer needs a health signal; /api/health is the only open JSON endpoint.
    assert svc.get("healthcheck"), "9router has no healthcheck"

    print(f"OK: {COMPOSE} satisfies AUT-4503 invariants")


if __name__ == "__main__":
    main()
