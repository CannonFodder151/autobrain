#!/usr/bin/env bash
# Mirror the shared Flutter lineage + version from the monorepo frontend into
# autobrain-mobile so the store app stays in sync with the server build.
#
#   ./scripts/sync-mobile.sh <path-to-autobrain-mobile-checkout>
#
# Copies frontend/lib + assets + the shared CHANGELOG into the mobile checkout,
# then bumps the mobile version to match the server APP_VERSION (build number
# incremented). pubspec.yaml dependencies are NOT copied — mobile keeps its own
# (with mobile-only deltas like package_info_plus). Mobile-only deltas preserved:
#   - lib/core/version_check.dart            (mobile-only file)
#   - lib/core/auth_state.dart               (update-available prompt logic)
#   - lib/core/config.dart                   (storeBuild, AUT-610)
#   - lib/screens/auth/login_screen.dart     (Play Store update prompt)
#   - lib/screens/settings/license_screen.dart (store-native IAP UI, AUT-610)
#   - lib/services/iap_service.dart (singleton IapService + IapCatalog/IapProduct, AUT-610)
#   - lib/services/car/car_kit_trip_monitor.dart (phone-path GPS types)
#   - lib/services/car/car_kit_service.dart (phone-path GPS position wiring,
#     AUT-427; the shared base must stay position-free for the web build)
#   - package_info_plus pubspec dependency   (mobile-only)
# If the shared base of auth_state.dart / config.dart / login_screen.dart /
# license_screen.dart / iap_service.dart / car_kit_trip_monitor.dart changes
# on the web side, a human must re-merge the mobile deltas on top — the script
# refuses to silently drop them.
set -euo pipefail

MOBILE="${1:?Usage: sync-mobile.sh <path-to-autobrain-mobile>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONT="$ROOT/frontend"

cd "$MOBILE"
[[ -d .git ]] || { echo "::error::$MOBILE is not a git checkout" >&2; exit 1; }

# --- Shared lineage (lib + assets + CHANGELOG) -------------------------------
# Copy lib/ verbatim except the mobile-only-delta files.
for f in core/auth_state.dart core/config.dart \
    screens/auth/login_screen.dart screens/settings/license_screen.dart \
    services/iap_service.dart \
    services/car/car_kit_trip_monitor.dart services/car/car_kit_service.dart; do
  [[ -f "lib/$f" ]] || { echo "::error::lib/$f missing in mobile checkout" >&2; exit 1; }
done
cp -a "$FRONT/lib/." lib/
# Restore the mobile-only deltas that cp just overwrote (frontend base + deltas
# live in the mobile repo; the web copy would drop the mobile-only features:
# the update prompt, the storeBuild/IAP UI, the singleton IAP service, and the
# phone-path GPS types — GpsFix/PositionSource — used by position_source*.dart).
git checkout -- lib/core/auth_state.dart lib/core/config.dart \
  lib/screens/auth/login_screen.dart lib/screens/settings/license_screen.dart \
  lib/services/iap_service.dart \
  lib/services/car/car_kit_trip_monitor.dart \
  lib/services/car/car_kit_service.dart 2>/dev/null || true
cp -a "$FRONT/assets/." assets/ 2>/dev/null || true
cp "$ROOT/CHANGELOG.md" CHANGELOG.md

# --- Dependency guard ---------------------------------------------------------
# lib/ sync can pull in new `package:` imports whose deps are not declared in
# the mobile pubspec.yaml (AUT-455: trip_route_map.dart -> flutter_map/
# latlong2/geolocator). pubspec.lock only resolves packages reachable from the
# declared dependencies, so any import missing from it breaks `flutter test`
# and every build. Fail the sync instead of pushing a broken lib/.
missing="$(grep -rhoE "^import 'package:[a-z_0-9]+/" lib --include='*.dart' \
  | sed -E "s/.*package:([a-z_0-9]+)\/.*/\1/" | sort -u \
  | while read -r pkg; do grep -q "^  $pkg:" pubspec.lock || echo "$pkg"; done)"
if [[ -n "$missing" ]]; then
  echo "::error::lib/ imports packages missing from pubspec.yaml: $(echo $missing | tr '\n' ' ')" >&2
  echo "::error::Add them to pubspec.yaml first (match frontend/pubspec.yaml versions), run flutter pub get, commit the lockfile." >&2
  exit 1
fi

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
