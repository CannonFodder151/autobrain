#!/usr/bin/env bash
# Runnable self-check for scripts/bump-version.sh (AUT-4855).
#
# The script prints copy-pasteable `docker build` lines. It used to interpolate
# "$CARTO_API_KEY" while only *printing* them, so under `set -u` (how CI invokes
# it, via auto-bump.sh) an unset CARTO_API_KEY killed the release bump while it
# was still printing its own help text. This check runs the real script in a
# sandbox with the key unset and set, asserting exit 0 both times, that the
# printed command carries a literal placeholder rather than an empty
# --build-arg, and that the version bump still lands.
#
#   ./scripts/test-bump-version.sh
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Minimal repo tree the script touches: config.py, ai/app/main.py,
# frontend/pubspec.yaml, CHANGELOG.md.
sandbox() {
  local w
  w="$(mktemp -d)"
  mkdir -p "$w/scripts" "$w/backend/app/core" "$w/ai/app" "$w/frontend"
  cp "$SRC/scripts/bump-version.sh" "$w/scripts/"
  printf 'APP_VERSION: str = "0.0.1"\n' >"$w/backend/app/core/config.py"
  printf 'V = os.environ.get("APP_VERSION", "0.0.1")\n' >"$w/ai/app/main.py"
  printf 'name: fb\nversion: 0.0.1+1\n' >"$w/frontend/pubspec.yaml"
  printf '## [Unreleased]\n- a change\n' >"$w/CHANGELOG.md"
  printf '%s' "$w"
}

fail=0
ok()   { echo "ok   [$1] exit=$2"; }
bad()  { echo "FAIL [$1]: $2" >&2; fail=1; }

# 1. CARTO_API_KEY unset — the regression. bump-version.sh runs its own
#    `set -euo pipefail`, so this is the exact CI condition.
w="$(sandbox)"; set +e
out="$(env -u CARTO_API_KEY bash "$w/scripts/bump-version.sh" 9.9.9 2>&1)"; rc=$?
set -e
if [[ "$rc" != 0 ]]; then bad "carto-unset" "exit $rc: $(tail -1 <<<"$out")"
elif [[ "$out" == *"unbound variable"* ]]; then bad "carto-unset" "unbound variable in output"
elif [[ "$out" != *'CARTO_API_KEY=$CARTO_API_KEY'* ]]; then bad "carto-unset" "no literal placeholder printed"
else ok "carto-unset" "$rc"; fi

# 2. Same run also proves the version bump landed.
if grep -q 'APP_VERSION: str = "9.9.9"' "$w/backend/app/core/config.py" \
  && grep -q 'version: 9.9.9+2' "$w/frontend/pubspec.yaml" \
  && grep -q '^## \[9.9.9\]' "$w/CHANGELOG.md"; then
  ok "applies-version" 0
else bad "applies-version" "version not applied"; fi
rm -rf "$w"

# 3. CARTO_API_KEY exported — must still print the literal placeholder (the
#    line is an instruction for a human, not a command that gets run).
w="$(sandbox)"; set +e
out="$(CARTO_API_KEY=pk-test bash "$w/scripts/bump-version.sh" 9.9.9 2>&1)"; rc=$?
set -e
if [[ "$rc" == 0 && "$out" == *'CARTO_API_KEY=$CARTO_API_KEY'* ]]; then
  ok "carto-set" "$rc"
else bad "carto-set" "exit $rc / placeholder missing"; fi
rm -rf "$w"

[[ "$fail" == 0 ]] && echo "PASS: bump-version.sh survives an unset CARTO_API_KEY"
exit "$fail"
