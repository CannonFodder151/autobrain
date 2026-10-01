#!/usr/bin/env bash
# Guard test for the editor-backup pre-flight in scripts/sync-mobile.sh (AUT-4919).
#
# The sync script needs a real git checkout, ios/ and android/ dirs, a populated
# frontend/ and a pubspec.lock, so this builds a throwaway fixture repo and runs
# the real script against it. Asserts:
#   1. a clean fixture gets past the guard (no false positive),
#   2. a *.bak in the mobile tree aborts the sync (exit 1),
#   3. a *.bak in the frontend lineage aborts the sync (exit 1),
#   4. a *~ backup is caught too,
#   5. the abort happens BEFORE any file is copied (no partial sync).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYNC="$ROOT/scripts/sync-mobile.sh"

fails=0
ok()   { echo "  ok   - $1"; }
fail() { echo "  FAIL - $1" >&2; fails=$((fails+1)); }

# Build a minimal fixture: a "frontend" lineage and a mobile checkout.
make_fixture() {
  local d; d="$(mktemp -d)"
  mkdir -p "$d/frontend/lib/core" "$d/frontend/assets" "$d/scripts"
  printf 'void main() {}\n' > "$d/frontend/lib/core/app.dart"
  echo '{}' > "$d/frontend/assets/data.json"
  printf 'version: 1.2.3\n' > "$d/frontend/pubspec.yaml"
  printf '# Changelog\n' > "$d/CHANGELOG.md"
  # Only the guard's inputs are needed; stub the rest so ROOT resolves here.
  cp "$SYNC" "$d/scripts/sync-mobile.sh"
  chmod +x "$d/scripts/sync-mobile.sh"
  mkdir -p "$d/scripts"; echo '{}' > "$d/scripts/auto-fix-mobile-test-mocks.py"

  mkdir -p "$d/mobile/lib/core" "$d/mobile/assets" "$d/mobile/ios" "$d/mobile/android"
  cp "$d/frontend/lib/core/app.dart" "$d/mobile/lib/core/app.dart"
  echo '{}' > "$d/mobile/assets/data.json"
  printf 'name: m\nversion: 1.2.3+1\n' > "$d/mobile/pubspec.yaml"
  printf 'packages:\n' > "$d/mobile/pubspec.lock"
  printf '# Changelog\n' > "$d/mobile/CHANGELOG.md"
  # Satisfy the mobile-only-delta pre-flight so a backup file is the ONLY
  # reason the sync can fail in these cases.
  for f in core/auth_state.dart core/config.dart \
      screens/auth/login_screen.dart screens/settings/license_screen.dart \
      services/iap_service.dart \
      services/car/car_kit_trip_monitor.dart services/car/car_kit_service.dart; do
    mkdir -p "$d/mobile/lib/$(dirname "$f")" "$d/frontend/lib/$(dirname "$f")"
    echo '// delta' > "$d/mobile/lib/$f"
    echo '// base'  > "$d/frontend/lib/$f"
  done
  ( cd "$d/mobile" && git init -q . && git add -A && git -c user.email=t@t -c user.name=t commit -qm init )
  echo "$d"
}

FIX="$(make_fixture)"
trap 'rm -rf "$FIX"' EXIT

# run_sync <label> -> sets OUT (stdout+stderr) and RC. Asserts guard did not fire
# by checking for the guard's own error marker.
run_sync() {
  set +e
  OUT="$(cd "$FIX/mobile" && bash "$FIX/scripts/sync-mobile.sh" "$FIX/mobile" 2>&1)"
  RC=$?
  set -e
}

echo "== 1. clean fixture must pass the guard (no false positive) =="
run_sync
if printf '%s' "$OUT" | grep -q 'editor backup files found'; then
  fail "clean fixture was blocked by the backup guard"
else
  ok "clean fixture not blocked"
fi

echo "== 2. *.bak in the mobile tree must abort the sync =="
echo x > "$FIX/mobile/CHANGELOG.md.bak"
run_sync
if [[ $RC -eq 1 ]] && printf '%s' "$OUT" | grep -q 'editor backup files found'; then
  ok "mobile-tree *.bak aborted the sync (rc=$RC)"
else
  fail "mobile-tree *.bak did not abort (rc=$RC): $OUT"
fi
rm -f "$FIX/mobile/CHANGELOG.md.bak"

echo "== 3. *.bak in the frontend lineage must abort the sync =="
echo x > "$FIX/frontend/lib/core/config.dart.bak"
run_sync
if [[ $RC -eq 1 ]] && printf '%s' "$OUT" | grep -q 'editor backup files found'; then
  ok "frontend *.bak aborted the sync (rc=$RC)"
else
  fail "frontend *.bak did not abort (rc=$RC): $OUT"
fi

echo "== 4. abort happens BEFORE any copy (no partial sync) =="
# Replace the mobile copy with a marker; if the guard is a pre-flight, the
# marker survives untouched.
echo "SENTINEL" > "$FIX/mobile/lib/core/app.dart"
run_sync
if grep -q 'SENTINEL' "$FIX/mobile/lib/core/app.dart"; then
  ok "no files were copied before the guard fired"
else
  fail "sync copied files before the guard fired (guard is not a pre-flight)"
fi
rm -f "$FIX/frontend/lib/core/config.dart.bak"

echo "== 5. *~ emacs backup must abort the sync =="
echo x > "$FIX/mobile/lib/core/app.dart~"
run_sync
if [[ $RC -eq 1 ]] && printf '%s' "$OUT" | grep -q 'editor backup files found'; then
  ok "mobile-tree *~ aborted the sync (rc=$RC)"
else
  fail "mobile-tree *~ did not abort (rc=$RC): $OUT"
fi
rm -f "$FIX/mobile/lib/core/app.dart~"

echo "== 6. after cleanup the sync proceeds again =="
run_sync
if printf '%s' "$OUT" | grep -q 'editor backup files found'; then
  fail "sync still blocked after backups were removed"
else
  ok "sync unblocked once backups were removed"
fi

if [[ $fails -gt 0 ]]; then
  echo "FAILED: $fails check(s)" >&2
  exit 1
fi
echo "PASS: all backup-guard checks"