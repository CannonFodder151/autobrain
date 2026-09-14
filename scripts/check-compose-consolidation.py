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

    # C4: ai service (gateway + market-data) remains intact.
    if "ai" not in svcs:
        errors.append("`ai` service missing")
    ai_env = svcs.get("ai", {}).get("environment") or {}
    if "API_KEY_FILE" not in ai_env:
        errors.append("ai env missing market-data API_KEY_FILE")

    if errors:
        print("\n".join(f"FAIL: {e}" for e in errors))
        sys.exit(1)
    print(f"OK: {COMPOSE} satisfies AUT-3153 consolidation invariants")


if __name__ == "__main__":
    main()
