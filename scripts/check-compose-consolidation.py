#!/usr/bin/env python3
"""Structural checks for the consolidated hosted compose file.

Covers AUT-3153 (worker merged), AUT-3824 (ai gateway merged), AUT-3810
(market-data merged) and AUT-3944 (single `backup` service).

Run: python3 scripts/check-compose-consolidation.py
No docker daemon needed — validates YAML/anchors and consolidation invariants.
"""
import sys

import yaml


COMPOSE = "docker-compose.hosted.yml"

# Services merged into `backend` or removed outright; none may come back.
RETIRED = ("worker", "ai", "market-data", "backup-agent")

# The hosted stack as consolidated: 9 long-running containers.
# `gh-runner` is NOT here — AUT-4911 moved it to its own Portainer stack
# (`gh-runner-autobrain-arm64`, stack 123 on EP5) because its image was
# unpublished. It was still listed until now, which kept this check red on
# main (AUT-5031) and therefore unenforced.
EXPECTED = {
    "postgres", "redis", "minio", "backend", "dongle-server",
    "frontend", "hub", "9router", "backup",
}


def main():
    with open(COMPOSE) as f:
        doc = yaml.safe_load(f)
    svcs = doc["services"]
    errors = []

    for name in RETIRED:
        if name in svcs:
            errors.append(f"retired `{name}` service is back in the hosted stack")
        if name == "backup-agent" and "autobrain-backup" in svcs:
            errors.append("`autobrain-backup` still present — AUT-3944 renamed it to `backup`")

    # AUT-3944: exactly one backup service, and it is the GUI (still :8080).
    if "backup" not in svcs:
        errors.append("`backup` service missing (AUT-3944)")
    else:
        backup = svcs["backup"]
        ports = [str(p) for p in (backup.get("ports") or [])]
        if not any(p.endswith(":8080") and p.startswith("127.0.0.1:") for p in ports):
            errors.append(f"`backup` GUI port binding changed; expected 127.0.0.1:8080:8080, got {ports}")

    # AUT-3944: the hourly push must address the service by its NEW dns name,
    # otherwise compose defaults and the running stack disagree.
    backend_env = svcs.get("backend", {}).get("environment") or {}
    url = str(backend_env.get("BACKUP_OFFSITE_URL", ""))
    if "autobrain-backup:" in url:
        errors.append(f"BACKUP_OFFSITE_URL still points at the old dns name: {url}")
    if "backup:" not in url:
        errors.append(f"BACKUP_OFFSITE_URL does not target the `backup` service: {url}")
    if str(backend_env.get("BACKUP_OFFSITE_ENABLED")).lower() != "true":
        errors.append("BACKUP_OFFSITE_ENABLED must stay \"true\" or hourly backups stop")

    # AUT-3153: backend carries the worker topology (Celery worker+beat).
    backend_cmd = svcs["backend"].get("command") or ""
    if isinstance(backend_cmd, list):
        backend_cmd = " ".join(backend_cmd)
    if "celery" not in backend_cmd or "worker" not in backend_cmd or "-B" not in backend_cmd:
        errors.append("backend command missing Celery worker+beat (-B)")

    # AUT-3824: the AI gateway is a co-process on :8001 inside `backend`.
    if "8001" not in backend_cmd:
        errors.append("backend command missing the AI gateway uvicorn on :8001 (AUT-3824)")

    # AUT-3153/AUT-3810/AUT-2195: fuel-poll secret files moved into backend env.
    for key in (
        "FUEL_NSW_API_KEY_FILE", "FUEL_NSW_API_SECRET_FILE",
        "FUEL_VIC_API_KEY_FILE", "FUEL_VIC_API_SECRET_FILE",
        "FUEL_QLD_API_KEY_FILE", "FUEL_SA_API_KEY_FILE",
    ):
        if key not in backend_env:
            errors.append(f"backend env missing {key}")

    # C4: the standalone `ai` service (gateway + market-data) is gone — the
    # gateway merged into backend (AUT-3153 follow-up, AUT-3824), so the
    # invariant is that backend carries the gateway's secret-file indirection.
    if "ai" in svcs:
        errors.append("standalone `ai` service is back (should be merged into backend)")
    for key in ("AI_GATEWAY_API_KEY_FILE", "AI_ROUTER_API_KEY_FILE"):
        if key not in backend_env:
            errors.append(f"backend env missing merged-gateway {key}")

    if set(svcs) != EXPECTED:
        errors.append(
            f"service set drifted: unexpected={sorted(set(svcs) - EXPECTED)} "
            f"missing={sorted(EXPECTED - set(svcs))}"
        )

    if errors:
        print("\n".join(f"FAIL: {e}" for e in errors))
        sys.exit(1)
    print(f"OK: {COMPOSE} is consolidated into {len(EXPECTED)} services ({', '.join(sorted(EXPECTED))})")


if __name__ == "__main__":
    main()
