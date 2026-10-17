#!/bin/sh
# Seed the AutoBrain Shop secret dir from a Portainer stack env dump.
# Usage: sudo ./scripts/seed-shop-secrets.sh stack-env.txt [/data/autobrain-shop/secrets]
set -eu

ENV_FILE="${1:?usage: seed-shop-secrets.sh <stack-env-file> [secrets-dir]}"
DIR="${2:-/data/autobrain-shop/secrets}"

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
        -e 's/^GITHUB_PAT$/github_pat/' \
        -e 's/^AI_ROUTER_API_KEY$/ai_router_api_key/' \
        -e 's/^AI_GATEWAY_API_KEY$/ai_gateway_api_key/' \
        -e 's/^REGO_LOOKUP_API_KEY$/rego_lookup_api_key/' \
        -e 's/^MARKET_DATA_API_KEY$/market_data_api_key/' \
        -e 's/^CARTO_API_KEY$/carto_api_key/' \
        -e 's/^FUEL_NSW_API_KEY$/fuel_nsw_api_key/' \
        -e 's/^FUEL_NSW_API_SECRET$/fuel_nsw_api_secret/' \
        -e 's/^FUEL_VIC_API_KEY$/fuel_vic_api_key/' \
        -e 's/^FUEL_VIC_API_SECRET$/fuel_vic_api_secret/' \
        -e 's/^FUEL_QLD_API_KEY$/fuel_qld_api_key/' \
        -e 's/^FUEL_SA_API_KEY$/fuel_sa_api_key/' \
        -e 's/^SMTP_USERNAME$/smtp_username/' \
        -e 's/^SMTP_PASSWORD$/smtp_password/' \
        -e 's/^ADMIN_INITIAL_PASSWORD$/admin_initial_password/' \
        -e 's/^ADMIN_API_KEY$/admin_api_key/' \
        -e 's/^DONGLE_SERVER_API_KEY$/dongle_server_api_key/' \
        -e 's/^DONGLE_WEB_BASIC_PASSWORD$/dongle_web_basic_password/' \
        -e 's/^STRIPE_SECRET_KEY$/stripe_secret_key/' \
        -e 's/^STRIPE_WEBHOOK_SECRET$/stripe_webhook_secret/' \
        -e 's/^IAP_APPLE_PRIVATE_KEY$/iap_apple_private_key/' \
    )
    # If name matched a known secret, write it; skip non-secret env vars.
    case "$name" in
        *_key|*_secret|*_password|*_token) ;;
        *) continue ;;
    esac
    printf '%s' "$val" > "$DIR/$name"
    chmod 0640 "$DIR/$name"
    chown root:1000 "$DIR/$name"
    echo "[seed] $name -> $DIR/$name"
done < "$ENV_FILE"

echo "[seed] done — secrets dir: $DIR"
echo "[seed] remember to shred $ENV_FILE"
