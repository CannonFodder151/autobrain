#!/usr/bin/env bash
# Mirror the shared Flutter lineage + version from the monorepo frontend into
# autobrain-mobile so the store app stays in sync with the server build.
#
#   ./scripts/sync-mobile.sh <path-to-autobrain-mobile-checkout>
#
# Copies frontend/lib, frontend/assets, pubspec.yaml and the shared CHANGELOG
# into the mobile checkout, then bumps the mobile version to match the server
# APP_VERSION (build number incremented). Mobile-only deltas are preserved:
#   - lib/core/version_check.dart            (mobile-only file)
#   - lib/core/auth_state.dart               (update-available prompt logic)
#   - lib/screens/auth/login_screen.dart     (Play Store update prompt)
#   - lib/services/car/car_kit_trip_monitor.dart (phone-path GPS types)
#   - package_info_plus pubspec dependency   (mobile-only)
# If the shared base of auth_state.dart / login_screen.dart changes on the web
# side, a human must re-merge the mobile deltas on top — the script refuses to
# silently drop them.
set -euo pipefail

MOBILE="${1:?Usage: sync-mobile.sh <path-to-autobrain-mobile>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONT="$ROOT/frontend"

cd "$MOBILE"
[[ -d .git ]] || { echo "::error::$MOBILE is not a git checkout" >&2; exit 1; }

# --- Shared lineage (lib + assets + CHANGELOG) -------------------------------
# Copy lib/ verbatim except the mobile-only-delta files.
for f in core/auth_state.dart screens/auth/login_screen.dart services/car/car_kit_trip_monitor.dart; do
  [[ -f "lib/$f" ]] || { echo "::error::lib/$f missing in mobile checkout" >&2; exit 1; }
done
cp -a "$FRONT/lib/." lib/
# Restore the mobile-only deltas that cp just overwrote (frontend base + deltas
# live in the mobile repo; the web copy would drop the update-prompt feature and
# the phone-side GPS types — GpsFix/PositionSource — used by position_source*.dart).
git checkout -- lib/core/auth_state.dart lib/screens/auth/login_screen.dart lib/services/car/car_kit_trip_monitor.dart 2>/dev/null || true
cp -a "$FRONT/assets/." assets/ 2>/dev/null || true
cp "$ROOT/CHANGELOG.md" CHANGELOG.md

# --- Version -----------------------------------------------------------------
SERVER="$(grep -E '^version: ' "$FRONT/pubspec.yaml" | head -1 | awk '{print $2}')"
SERVER_X_Y_Z="${SERVER%%+*}"
MOB_CUR="$(grep -E '^version: ' pubspec.yaml | head -1 | awk '{print $2}')"
MOB_BUILD="$(echo "$MOB_CUR" | sed -E 's/^[0-9]+\.[0-9]+\.[0-9]+\+?([0-9]*).*/\1/')"
[[ -n "$MOB_BUILD" ]] || MOB_BUILD=0
NEW_BUILD=$((MOB_BUILD + 1))
NEW="$SERVER_X_Y_Z+$NEW_BUILD"

sed -i -E "s/^version: [0-9.]+.*/version: $NEW/" pubspec.yaml
echo "mobile version: $MOB_CUR -> $NEW (matches server $SERVER_X_Y_Z)"

echo "==> synced. Review changes in $MOBILE, commit and push."
