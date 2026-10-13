#!/usr/bin/env python3
"""AUT-3153: structural checks for the consolidated hosted compose file.

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

    # C1: the standalone worker service is gone from the hosted stack.
    if "worker" in svcs:
        errors.append("standalone `worker` service still present")

    # C2: backend now carries the worker topology (Celery worker+beat).
    backend_cmd = svcs["backend"].get("command") or ""
    if isinstance(backend_cmd, list):
        backend_cmd = " ".join(backend_cmd)
    if "celery" not in backend_cmd or "worker" not in backend_cmd or "-B" not in backend_cmd:
        errors.append("backend command missing Celery worker+beat (-B)")

    # AUT-3824: the AI gateway is a co-process on :8001 inside `backend`.
    if "8001" not in backend_cmd:
        errors.append("backend command missing the AI gateway uvicorn on :8001 (AUT-3824)")

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

    backend_env = svcs["backend"].get("environment") or {}
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

    # AUT-3944: backup service must exist with GUI port bound to loopback 8080.
    if "backup" not in svcs:
        errors.append("`backup` service missing (AUT-3944)")
    else:
        backup_ports = [str(p) for p in (svcs["backup"].get("ports") or [])]
        if not any(p.endswith(":8080") and p.startswith("127.0.0.1:") for p in backup_ports):
            errors.append("`backup` GUI port binding changed — must stay on 127.0.0.1:8080 (AUT-3944)")

    # AUT-3944: BACKUP_OFFSITE_URL must target the `backup` service.
    offsite_url = str(backend_env.get("BACKUP_OFFSITE_URL", ""))
    if "autobrain-backup:" in offsite_url:
        errors.append("BACKUP_OFFSITE_URL still points at the old dns name (AUT-3944)")
    elif "backup:" not in offsite_url:
        errors.append("BACKUP_OFFSITE_URL does not target the `backup` service (AUT-3944)")

    # AUT-3944: BACKUP_OFFSITE_ENABLED must stay true.
    offsite_enabled = str(backend_env.get("BACKUP_OFFSITE_ENABLED", "")).lower()
    if offsite_enabled != "true":
        errors.append('BACKUP_OFFSITE_ENABLED must stay "true" (AUT-3944)')

    if errors:
        print("\n".join(f"FAIL: {e}" for e in errors))
        sys.exit(1)
    print(
        f"OK: {COMPOSE} satisfies AUT-3153 consolidation invariants "
        f"({len(svcs)} services: {', '.join(sorted(svcs))})"
    )


if __name__ == "__main__":
    main()
