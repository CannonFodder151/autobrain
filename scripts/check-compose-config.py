#!/usr/bin/env python3
"""AUT-1533: structural checks for the hardened hosted compose file.

Run: python3 scripts/check-compose-config.py
No docker daemon needed — validates YAML/anchors and remediation invariants.

AUT-4678: services referenced by the F2 loops are optional after the AUT-3153
merge (there is no standalone `ai` service any more) — index them only when
present so a service removal degrades coverage instead of crashing the guard.
"""
import sys

import yaml

COMPOSE = "docker-compose.hosted.yml"
SECRET_FILES = {
    "postgres_password", "redis_password", "minio_access_key", "minio_secret_key",
    "backend_secret_key", "ai_router_api_key", "ai_gateway_api_key",
    "market_data_api_key", "rego_lookup_api_key", "admin_initial_password",
    "admin_api_key", "smtp_username", "smtp_password", "stripe_secret_key",
    "stripe_webhook_secret", "iap_google_service_account_json",
    "iap_apple_private_key", "hub_hosted_registration_key",
    # AUT-1858 fuel feeds (AUT-1813/AUT-1932/AUT-2218/AUT-2610) + dongle backchannel (AUT-1673).
    "fuel_nsw_api_key", "fuel_nsw_api_secret", "fuel_vic_api_key",
    "fuel_vic_api_secret", "fuel_qld_api_key", "fuel_sa_api_key",
    "dongle_server_api_key", "dongle_web_basic_password",
    # AUT-4678: github_pat, seeded by scripts/seed-secrets.sh for gh-runner.
    "github_pat",
    # AUT-3827/AUT-3944 off-site backup push keys (backend -> autobrain-backup).
    "backup_offsite_gui_key", "backup_offsite_ingest_key",
}
# Services whose secret handling this check inspects. Any of these may be
# absent after a consolidation merge — the loops filter by presence.
SECRET_SERVICES = ("postgres", "backend", "ai")
PLAIN_FORBIDDEN = {  # secret-class keys that must not appear as plain env in app services
    "POSTGRES_PASSWORD", "SECRET_KEY", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY",
    "AI_GATEWAY_API_KEY", "AI_ROUTER_API_KEY", "REGO_LOOKUP_API_KEY",
    "MARKET_DATA_API_KEY", "ADMIN_INITIAL_PASSWORD", "ADMIN_API_KEY",
    "SMTP_USERNAME", "SMTP_PASSWORD", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
    "IAP_GOOGLE_SERVICE_ACCOUNT_JSON", "IAP_APPLE_PRIVATE_KEY",
    "SOCIAL_FEDERATION_HOSTED_REGISTRATION_KEY",
    "BACKUP_OFFSITE_GUI_KEY", "BACKUP_OFFSITE_INGEST_KEY",
}


def env_of(svc):
    return (svc or {}).get("environment") or {}


def present(svcs, names):
    """Names that actually exist in the compose file (AUT-4678)."""
    return [n for n in names if n in svcs]


def main():
    with open(COMPOSE) as f:
        doc = yaml.safe_load(f)
    svcs = doc["services"]
    errors = []

    # F1/F2: every bind-mounted secret path resolves inside /run/secrets.
    mounted = set()
    for name, svc in svcs.items():
        for vol in svc.get("volumes") or []:
            if not isinstance(vol, dict):
                continue
            target = str(vol.get("target", ""))
            if target == "/run/secrets":
                mounted |= SECRET_FILES  # whole secrets dir mounted read-only
            elif target.startswith("/run/secrets/"):
                mounted.add(target.rsplit("/", 1)[-1])
        if name == "redis":  # long-form only via list above; also check command
            cmd = " ".join(svc.get("command") or [])
            assert "/run/secrets/redis_password" in cmd, "redis requirepass must read the secret file"
    missing = SECRET_FILES - mounted
    if missing:
        errors.append(f"secrets never bind-mounted into any service: {sorted(missing)}")

    # F1: redis healthcheck uses the password file, not bare ping.
    hc = svcs["redis"]["healthcheck"]["test"]
    hc = hc if isinstance(hc, str) else " ".join(hc)
    assert "/run/secrets/redis_password" in hc, f"redis healthcheck not authed: {hc!r}"

    # AUT-4038: pg_isready without -h uses the local unix socket, where
    # `local ... peer` auth compares the container's root OS user against the
    # POSTGRES_USER role and logs an auth failure every healthcheck interval.
    pg_hc = svcs["postgres"]["healthcheck"]["test"]
    pg_hc = pg_hc if isinstance(pg_hc, str) else " ".join(pg_hc)
    assert "-h 127.0.0.1" in pg_hc, (
        f"postgres healthcheck must use TCP (-h 127.0.0.1), not the peer-auth "
        f"unix socket: {pg_hc!r}"
    )

    # AUT-4678: no secret-class plain env left on the app services. The worker
    # service was merged into backend (AUT-3153) and the `ai` gateway/market-data
    # service into backend (AUT-3824), so neither exists separately any more —
    # hence the presence filter: the merged gateway keeps the secret-file
    # indirection via backend's *_FILE entries.
    for svc_name in present(svcs, ("backend",)):
        plain = PLAIN_FORBIDDEN & set(env_of(svcs[svc_name]))
        if plain:
            errors.append(f"{svc_name} still carries plain secret env: {sorted(plain)}")

    # F2: *_FILE references point at seeded files.
    for svc_name in present(svcs, SECRET_SERVICES):
        for k, v in env_of(svcs[svc_name]).items():
            if k.endswith("_FILE"):
                fname = v.rsplit("/", 1)[-1]
                if fname not in SECRET_FILES:
                    errors.append(f"{svc_name}: {k} -> unknown secret file {fname!r}")

    # F3: 9router digest pin.
    img = svcs["9router"]["image"]
    assert "@sha256:" in img, f"9router not digest-pinned: {img}"

    # F5: frontend maps host 8086 to container 8080 (nginx-unprivileged).
    ports = [str(p) for p in svcs["frontend"]["ports"]]
    assert any("8086:8080" in p for p in ports), f"frontend port map wrong: {ports}"

    if errors:
        print("\n".join(f"FAIL: {e}" for e in errors))
        sys.exit(1)
    print(f"OK: {COMPOSE} satisfies AUT-1533 invariants")


if __name__ == "__main__":
    main()
