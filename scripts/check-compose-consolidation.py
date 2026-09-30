#!/usr/bin/env python3
"""AUT-3153: structural checks for the consolidated hosted compose file.

Run: python3 scripts/check-compose-consolidation.py
No docker daemon needed — validates YAML/anchors and consolidation invariants.
"""
import sys

import yaml


COMPOSE = "docker-compose.hosted.yml"


def main():
    with open(COMPOSE) as f:
        doc = yaml.safe_load(f)
    svcs = doc["services"]
    errors = []

    # C1: the standalone worker service is gone from the hosted stack.
    if "worker" in svcs:
        errors.append("standalone `worker` service still present")

    # C2: backend now carries the worker topology (Celery worker+beat).
    backend_cmd = svcs["backend"].get("command") or ""
    if isinstance(backend_cmd, list):
        backend_cmd = " ".join(backend_cmd)
    if "celery" not in backend_cmd or "worker" not in backend_cmd or "-B" not in backend_cmd:
        errors.append("backend command missing Celery worker+beat (-B)")

    # C3: worker fuel-poll secrets moved into the backend environment.
    backend_env = svcs["backend"].get("environment") or {}
    for key in (
        "FUEL_NSW_API_KEY_FILE", "FUEL_NSW_API_SECRET_FILE",
        "FUEL_VIC_API_KEY_FILE", "FUEL_VIC_API_SECRET_FILE",
        "FUEL_QLD_API_KEY_FILE", "FUEL_SA_API_KEY_FILE",
    ):
        if key not in backend_env:
            errors.append(f"backend env missing {key}")

    # C4: the AI gateway is merged into the backend (no standalone ai service).
    for gone in ("ai", "market-data"):
        if gone in svcs:
            errors.append(f"standalone `{gone}` service still present")
    if "ai_app.main:app" not in backend_cmd or "8001" not in backend_cmd:
        errors.append("backend command missing AI gateway (ai_app.main:app on :8001)")
    if backend_env.get("AI_LOCAL_BASE_URL") != "http://backend:8001":
        errors.append("backend AI_LOCAL_BASE_URL should point at itself (http://backend:8001)")
    for key in ("AI_GATEWAY_API_KEY_FILE", "AI_ROUTER_API_KEY_FILE"):
        if key not in backend_env:
            errors.append(f"backend env missing {key}")

    # C5: backup runs in the autobrain-backup service; no separate backup-agent.
    if "backup-agent" in svcs:
        errors.append("standalone `backup-agent` service still present")

    if errors:
        print("\n".join(f"FAIL: {e}" for e in errors))
        sys.exit(1)
    print(
        f"OK: {COMPOSE} satisfies AUT-3153 consolidation invariants "
        f"({len(svcs)} services: {', '.join(sorted(svcs))})"
    )


if __name__ == "__main__":
    main()
