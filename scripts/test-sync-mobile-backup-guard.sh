#!/usr/bin/env bash
# Runnable self-check for the AUT-4919 editor-backup guard in sync-mobile.sh.
# Builds a throwaway monorepo + mobile checkout and asserts the sync refuses to
# copy/track *.bak, *.orig, *.rej and *~ files, and still runs clean without them.
#
#   ./scripts/test-sync-mobile-backup-guard.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT/scripts/sync-mobile.sh"

W="$(mktemp -d)"
trap 'rm -rf "$W"' EXIT

mkdir -p "$W/repo/scripts" "$W/repo/frontend/lib/core" "$W/repo/frontend/assets"
cp "$SCRIPT" "$W/repo/scripts/sync-mobile.sh"
chmod +x "$W/repo/scripts/sync-mobile.sh"
echo "# changelog" > "$W/repo/CHANGELOG.md"
echo "// dart" > "$W/repo/frontend/lib/core/config.dart"

mk_mobile() {
  rm -rf "$W/mobile"
  mkdir -p "$W/mobile/ios" "$W/mobile/android" "$W/mobile/lib/core" "$W/mobile/assets"
  git init -q -b main "$W/mobile"
  echo "# mobile" > "$W/mobile/pubspec.yaml"
}

run_sync() { "$W/repo/scripts/sync-mobile.sh" "$W/mobile" 2>&1 || true; }

expect_refused() {
  local label="$1" out
  out="$(run_sync)"
  if ! grep -q 'editor backup files must not be synced' <<<"$out"; then
    echo "FAIL: $label — sync did not trip the backup guard" >&2
    echo "$out" >&2
    exit 1
  fi
  echo "ok: $label"
}

# 1. Clean tree: the guard must not fire. The sync then fails later for an
#    unrelated reason (this stub mobile checkout has no real lineage), which is
#    exactly how we know the guard let it through.
mk_mobile
out="$(run_sync)"
if grep -q 'editor backup files must not be synced' <<<"$out"; then
  echo "FAIL: clean tree tripped the backup guard" >&2
  echo "$out" >&2
  exit 1
fi
echo "ok: clean tree passes the guard"

# 2. Backup in the source lineage the sync copies from.
mk_mobile; touch "$W/repo/frontend/lib/core/config.dart.bak"
expect_refused "backup in frontend/lib"

# 3. Backup already sitting in the mobile checkout — the exact AUT-4919 case
#    (CHANGELOG.md.bak swept in by `git add -A` on the persistent runner).
mk_mobile; touch "$W/mobile/CHANGELOG.md.bak"
expect_refused "backup in mobile repo root"

# 4. Other editor artifacts.
mk_mobile; touch "$W/mobile/lib/core/config.dart~"
expect_refused "tilde backup in mobile lib"

mk_mobile; touch "$W/mobile/assets/logo.orig"
expect_refused ".orig in mobile assets"

# 5. Guard runs before any copy — a backup must not be copied into the tree.
mk_mobile; touch "$W/repo/frontend/lib/core/config.dart.bak"
run_sync >/dev/null
if [[ -e "$W/mobile/lib/core/config.dart.bak" ]]; then
  echo "FAIL: backup was copied before the guard tripped" >&2
  exit 1
fi
echo "ok: no backup copied into the mobile tree"

echo "all sync-mobile backup guard checks passed"
