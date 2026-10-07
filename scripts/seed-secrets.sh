#!/bin/sh
# AUT-1533: seed the secret dir from a Portainer-stack env dump.
# Usage: sudo ./scripts/seed-secrets.sh stack-env.txt [/data/autobrain/secrets]
#   AUT-1853: default target is /data/autobrain/secrets — NOT /opt/autobrain/secrets.
#   The snap dockerd on the Oracle VM masks host /opt (read-only core24 squashfs),
#   so bind-mounts under /opt fail. /data is daemon-visible and never masked.
#   stack-env.txt is KEY=VALUE lines (the current hosted stack env). Values are
#   written one-per-file, mode 0640 group 1000 (containers run uid 1000), then
#   the input file should be shredded. Idempotent; empty values -> empty file.
set -eu

ENV_FILE="${1:?usage: seed-secrets.sh <stack-env-file> [secrets-dir]}"
DIR="${2:-/data/autobrain/secrets}"

# KEY in stack env -> secret file name. Keys not listed here are non-secret
# config and stay in the Portainer stack env.
seed() {
    mkdir -p "$DIR"
    umask 077
    while IFS= read -r line; do
        case "$line" in ''|\#*) continue ;; esac
        key=${line%%=*}
        val=${line#*=}
        # NB: no comments inside the sed backslash continuation below — a `#` line
        # between two continued lines terminates the sed arg list (AUT-2241).
        # FUEL_VIC_API_KEY / FUEL_VIC_API_SECRET are intentionally unmapped
        # (AUT-4143): the VIC Servo Saver endpoint does not exist (NXDOMAIN).
        name=$(printf '%s\n' "$key" | sed \
            -e 's/^POSTGRES_PASSWORD$/postgres_password/' \
            -e 's/^SECRET_KEY$/backend_secret_key/' \
            -e 's/^MINIO_ACCESS_KEY$/minio_access_key/' \
            -e 's/^MINIO_SECRET_KEY$/minio_secret_key/' \
            -e 's/^REDIS_PASSWORD$/redis_password/' \
            -e 's/^GITHUB_PAT$/github_pat/' \
            -e 's/^AI_ROUTER_API_KEY$/ai_router_api_key/' \
            -e 's/^AI_GATEWAY_API_KEY$/ai_gateway_api_key/' \
            -e 's/^REGO_LOOKUP_API_KEY$/rego_lookup_api_key/' \
            -e 's/^MARKET_DATA_API_KEY$/market_data_api_key/' \
            -e 's/^CARTO_API_KEY$/carto_api_key/' \
            -e 's/^FUEL_NSW_API_KEY$/fuel_nsw_api_key/' \
            -e 's/^FUEL_NSW_API_SECRET$/fuel_nsw_api_secret/' \
            -e 's/^FUEL_QLD_API_KEY$/fuel_qld_api_key/' \
            -e 's/^FUEL_SA_API_KEY$/fuel_sa_api_key/' \
            -e 's/^DONGLE_SERVER_API_KEY$/dongle_server_api_key/' \
            -e 's/^DONGLE_WEB_BASIC_PASSWORD$/dongle_web_basic_password/' \
            -e 's/^ADMIN_INITIAL_PASSWORD$/admin_initial_password/' \
            -e 's/^ADMIN_API_KEY$/admin_api_key/' \
            -e 's/^SMTP_USERNAME$/smtp_username/' \
            -e 's/^SMTP_PASSWORD$/smtp_password/' \
            -e 's/^STRIPE_SECRET_KEY$/stripe_secret_key/' \
            -e 's/^STRIPE_WEBHOOK_SECRET$/stripe_webhook_secret/' \
            -e 's/^IAP_GOOGLE_SERVICE_ACCOUNT_JSON$/iap_google_service_account_json/' \
            -e 's/^IAP_APPLE_PRIVATE_KEY$/iap_apple_private_key/' \
            -e 's/^SOCIAL_FEDERATION_HOSTED_REGISTRATION_KEY$/hub_hosted_registration_key/' \
            -e 's/^BACKUP_OFFSITE_GUI_KEY$/backup_offsite_gui_key/' \
            -e 's/^BACKUP_OFFSITE_INGEST_KEY$/backup_offsite_ingest_key/' \
            -e 's/^DEMO_PASSWORD$/demo-account-password/')
        [ "$name" = "$key" ] && continue   # not a mapped secret — skip
        # AUT-2241: never overwrite an existing non-empty secret. The running
        # services already consumed the old value (postgres volume, redis
        # --requirepass, minio root creds, jwt SECRET_KEY), so overwriting the
        # file alone silently breaks auth while the file side looks correct.
        if [ -s "$DIR/$name" ] && [ "${SEED_ALLOW_OVERWRITE:-0}" != 1 ]; then
            echo "KEEP   $DIR/$name (exists; set SEED_ALLOW_OVERWRITE=1 to replace)"
            continue
        fi
        printf '%s' "$val" > "$DIR/$name"
        chown root:1000 "$DIR/$name" 2>/dev/null || \
            echo "warn: chown $DIR/$name failed (rootless/userns?) — check ownership manually"
        chmod 0640 "$DIR/$name"
        echo "seeded $DIR/$name"
    done < "$ENV_FILE"
    chgrp 1000 "$DIR" 2>/dev/null || true
    chmod 0750 "$DIR"
}

seed

# AB-INFRA-004: the broker password is new — generate one if the stack env had none.
if [ ! -s "$DIR/redis_password" ]; then
    val=$(openssl rand -hex 24 2>/dev/null) || val=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')
    printf '%s' "$val" > "$DIR/redis_password"
    chown root:1000 "$DIR/redis_password" 2>/dev/null || true
    chmod 0640 "$DIR/redis_password"
    echo "generated $DIR/redis_password"
fi

echo "Done. Remove the env dump now: shred -u $ENV_FILE"
