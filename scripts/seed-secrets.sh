#!/bin/sh
# AUT-1533: seed /opt/autobrain/secrets from a Portainer-stack env dump.
# Usage: sudo ./scripts/seed-secrets.sh stack-env.txt [/opt/autobrain/secrets]
#   stack-env.txt is KEY=VALUE lines (the current hosted stack env). Values are
#   written one-per-file, mode 0640 group 1000 (containers run uid 1000), then
#   the input file should be shredded. Idempotent; empty values -> empty file.
set -eu

ENV_FILE="${1:?usage: seed-secrets.sh <stack-env-file> [secrets-dir]}"
DIR="${2:-/opt/autobrain/secrets}"

# KEY in stack env -> secret file name. Keys not listed here are non-secret
# config and stay in the Portainer stack env.
seed() {
    mkdir -p "$DIR"
    umask 077
    while IFS= read -r line; do
        case "$line" in ''|\#*) continue ;; esac
        key=${line%%=*}
        val=${line#*=}
        name=$(printf '%s\n' "$key" | sed \
            -e 's/^POSTGRES_PASSWORD$/postgres_password/' \
            -e 's/^SECRET_KEY$/backend_secret_key/' \
            -e 's/^MINIO_ACCESS_KEY$/minio_access_key/' \
            -e 's/^MINIO_SECRET_KEY$/minio_secret_key/' \
            -e 's/^REDIS_PASSWORD$/redis_password/' \
            -e 's/^AI_ROUTER_API_KEY$/ai_router_api_key/' \
            -e 's/^AI_GATEWAY_API_KEY$/ai_gateway_api_key/' \
            -e 's/^REGO_LOOKUP_API_KEY$/rego_lookup_api_key/' \
            -e 's/^MARKET_DATA_API_KEY$/market_data_api_key/' \
            -e 's/^FUEL_NSW_API_KEY$/fuel_nsw_api_key/' \
            -e 's/^FUEL_NSW_API_SECRET$/fuel_nsw_api_secret/' \
            -e 's/^ADMIN_INITIAL_PASSWORD$/admin_initial_password/' \
            -e 's/^ADMIN_API_KEY$/admin_api_key/' \
            -e 's/^SMTP_USERNAME$/smtp_username/' \
            -e 's/^SMTP_PASSWORD$/smtp_password/' \
            -e 's/^STRIPE_SECRET_KEY$/stripe_secret_key/' \
            -e 's/^STRIPE_WEBHOOK_SECRET$/stripe_webhook_secret/' \
            -e 's/^IAP_GOOGLE_SERVICE_ACCOUNT_JSON$/iap_google_service_account_json/' \
            -e 's/^IAP_APPLE_PRIVATE_KEY$/iap_apple_private_key/' \
            -e 's/^SOCIAL_FEDERATION_HOSTED_REGISTRATION_KEY$/hub_hosted_registration_key/')
        [ "$name" = "$key" ] && continue   # not a mapped secret — skip
        printf '%s' "$val" > "$DIR/$name"
        chown root:1000 "$DIR/$name"
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
    chown root:1000 "$DIR/redis_password"
    chmod 0640 "$DIR/redis_password"
    echo "generated $DIR/redis_password"
fi

echo "Done. Remove the env dump now: shred -u $ENV_FILE"
