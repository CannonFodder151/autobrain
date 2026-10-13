#!/usr/bin/env python3
"""Structural checks for the consolidated hosted compose file.

Covers AUT-3153 (worker merged), AUT-3824 (ai gateway merged), AUT-3810
(market-data merged), AUT-3944 (single `backup` service), and AUT-6415
(dongle-server and backup GUI merged into backend).

Run: python3 scripts/check-compose-consolidation.py
No docker daemon needed — validates YAML/anchors and consolidation invariants.
"""
import sys

import yaml


COMPOSE = "docker-compose.hosted.yml"

# Services merged into `backend` or removed outright; none may come back.
RETIRED = ("worker", "ai", "market-data", "backup-agent", "dongle-server", "backup")

# The hosted stack as consolidated: 7 long-running containers.
# `gh-runner` is NOT here — AUT-4911 moved it to its own Portainer stack
# (`gh-runner-autobrain-arm64`, stack 123 on EP5) because its image was
# unpublished. It was still listed until now, which kept this check red on
# main (AUT-5031) and therefore unenforced.
EXPECTED = {
    "postgres", "redis", "minio", "backend",
    "frontend", "hub", "9router",
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

    # AUT-6415: dongle-server and backup GUI merged into backend.
    # Dongle-server runs on :8002, backup GUI runs on :8080 inside the backend container.
    # Both were previously separate services (dongle-server and backup).
    # BACKUP_OFFSITE_URL now points to localhost:8080.
    backend_env = svcs.get("backend", {}).get("environment") or {}
    url = str(backend_env.get("BACKUP_OFFSITE_URL", ""))
    if "autobrain-backup:" in url:
        errors.append(f"BACKUP_OFFSITE_URL still points at the old dns name: {url}")
    if "backup:" in url:
        errors.append(f"BACKUP_OFFSITE_URL should point to localhost, not `backup` service: {url}")
    # Allow variable interpolation ${BACKUP_OFFSITE_URL:-http://localhost:8080}
    if "localhost:8080" not in url and "127.0.0.1:8080" not in url:
        errors.append(f"BACKUP_OFFSITE_URL should target localhost:8080 for in-process backup GUI: {url}")
    if str(backend_env.get("BACKUP_OFFSITE_ENABLED")).lower() != "true":
        errors.append("BACKUP_OFFSITE_ENABLED must stay \"true\" or hourly backups stop")

    # AUT-1673: dongle-server backchannel now points to localhost:8002
    dongle_url = str(backend_env.get("DONGLE_SERVER_URL", ""))
    if dongle_url and "localhost:8002" not in dongle_url and "127.0.0.1:8002" not in dongle_url:
        errors.append(f"DONGLE_SERVER_URL should target localhost:8002 for in-process dongle-server: {dongle_url}")

    # AUT-3153: backend carries the worker topology (Celery worker+beat).
    backend_cmd = svcs["backend"].get("command") or ""
    if isinstance(backend_cmd, list):
        backend_cmd = " ".join(backend_cmd)
    if "celery" not in backend_cmd or "worker" not in backend_cmd or "-B" not in backend_cmd:
        errors.append("backend command missing Celery worker+beat (-B)")

    # AUT-3824: the AI gateway is a co-process on :8001 inside `backend`.
    if "8001" not in backend_cmd:
        errors.append("backend command missing the AI gateway uvicorn on :8001 (AUT-3824)")

    # AUT-6415: dongle-server and backup GUI uvicorn processes in backend command
    if "dongle_server.main:app" not in backend_cmd:
        errors.append("backend command missing dongle-server uvicorn on :8002 (AUT-6415)")
    if "backup_gui.main:app" not in backend_cmd:
        errors.append("backend command missing backup GUI uvicorn on :8080 (AUT-6415)")

    # AUT-5088: migrations must run at boot. Hosted was still on
    # `python -m app.db.bootstrap`, whose create_all fallback swallowed every
    # migration failure, so migration-only changes were dead code in prod.
    if "alembic upgrade head" not in backend_cmd:
        errors.append(
            "backend command missing `alembic upgrade head` (AUT-5088) — "
            "migrations are dead code without it"
        )
    elif backend_cmd.index("alembic upgrade head") > min(
        (backend_cmd.index(m) for m in ("python -m app.db.bootstrap", "uvicorn") if m in backend_cmd),
        default=len(backend_cmd),
    ):
        errors.append(
            "`alembic upgrade head` must run before bootstrap/uvicorn (AUT-5088)"
        )

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