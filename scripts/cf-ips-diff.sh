#!/usr/bin/env bash
# AUT-5695 / AUT-5460 drift guard: diff the `set_real_ip_from` trust boundary in
# the frontend nginx configs against Cloudflare's LIVE published edge ranges.
#
# Why this exists: the list in docker/frontend/nginx.conf and nginx-proxy.conf is
# a hand-copied mirror of https://www.cloudflare.com/ips-v4 + ips-v6. It already
# drifted once on main (198.41.128.0/17 was missing), and because the real peer
# is the docker-bridge proxy, a stale list is inert — the login lockout
# (AUT-3858/AUT-5460) silently re-opens instead of failing loudly.
#
# Usage: scripts/cf-ips-diff.sh
# Exit 0  -> every live Cloudflare range is trusted in BOTH configs.
# Exit 1  -> a range is missing or extra; prints the diff.
#
# Run from the repo root. No docker, no network auth — just curl to the two
# public Cloudflare endpoints. Fails closed: a fetch error is a failure.

set -euo pipefail

CF_V4="https://www.cloudflare.com/ips-v4"
CF_V6="https://www.cloudflare.com/ips-v6"
TIMEOUT="${CF_IPS_TIMEOUT:-20}"

# Configs that pin the Cloudflare trust boundary. Both must agree — a range
# trusted in one but not the other is a drift signal too.
# Override with CF_IPS_CONFS (space-separated) for tests that need a stale
# config without touching the real files.
if [ -n "${CF_IPS_CONFS:-}" ]; then
  read -ra CONFS <<< "$CF_IPS_CONFS"
else
  CONFS=(
    "docker/frontend/nginx.conf"
    "docker/frontend/nginx-proxy.conf"
  )
fi

# --- fetch live ranges --------------------------------------------------------

fetch() {
  local url="$1"
  curl -fsS --max-time "$TIMEOUT" "$url" || {
    echo "ERROR: could not fetch $url (curl failed)" >&2
    exit 2
  }
}

LIVE_V4="$(fetch "$CF_V4")"
LIVE_V6="$(fetch "$CF_V6")"

# --- extract `set_real_ip_from <range>;` from a conf file --------------------

conf_ranges() {
  local file="$1"
  if [ ! -f "$file" ]; then
    echo "ERROR: $file not found" >&2
    exit 2
  fi
  # `set_real_ip_from 173.245.48.0/20;` — one range per directive. Strip the
  # directive and trailing semicolon; tolerate leading whitespace.
  grep -E '^[[:space:]]*set_real_ip_from[[:space:]]+' "$file" \
    | sed -E 's/^[[:space:]]*set_real_ip_from[[:space:]]+//; s/[[:space:]]*;[[:space:]]*$//' \
    | sed -E 's/[[:space:]]+$//' \
    | sort -u
}

# --- diff ---------------------------------------------------------------------

rc=0

for conf in "${CONFS[@]}"; do
  if [ ! -f "$conf" ]; then
    echo "ERROR: $conf not found" >&2
    rc=2
    continue
  fi

  TRUSTED="$(conf_ranges "$conf")"

  # Every live range must be present in the conf.
  while IFS= read -r range; do
    [ -z "$range" ] && continue
    if ! grep -qFx "$range" <(printf '%s\n' "$TRUSTED"); then
      echo "MISSING in $conf: $range" >&2
      rc=1
    fi
  done < <(printf '%s\n' "$LIVE_V4" "$LIVE_V6")

  # No extra (stale / hand-typed) ranges beyond the live set.
  while IFS= read -r range; do
    [ -z "$range" ] && continue
    if ! grep -qFx "$range" <(printf '%s\n' "$LIVE_V4" "$LIVE_V6"); then
      echo "EXTRA in $conf (not in live Cloudflare list): $range" >&2
      rc=1
    fi
  done < <(printf '%s\n' "$TRUSTED")
done

if [ "$rc" -eq 0 ]; then
  echo "OK: Cloudflare edge ranges in ${CONFS[*]} match live ips-v4 + ips-v6"
fi

exit "$rc"