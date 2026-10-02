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
  local w cl
  cl="${1:-## [Unreleased]\n- a change\n}"
  w="$(mktemp -d)"
  mkdir -p "$w/scripts" "$w/backend/app/core" "$w/ai/app" "$w/frontend"
  cp "$SRC/scripts/bump-version.sh" "$w/scripts/"
  cp "$SRC/scripts/auto-bump.sh" "$w/scripts/"
  printf 'APP_VERSION: str = "0.0.1"\n' >"$w/backend/app/core/config.py"
  printf 'V = os.environ.get("APP_VERSION", "0.0.1")\n' >"$w/ai/app/main.py"
  printf 'name: fb\nversion: 0.0.1+1\n' >"$w/frontend/pubspec.yaml"
  printf '%b' "$cl" >"$w/CHANGELOG.md"
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

# 4. AUT-5139: the bot must PROMOTE the [Unreleased] body, not orphan it under
#    an empty heading. Security reported v0.3.297 looked like it inserted the
#    version heading after [Unreleased]; it actually replaces the heading and
#    re-opens an empty [Unreleased] above. Lock that in with a fixture that has
#    real content under [Unreleased] plus a previous release.
w="$(sandbox '## [Unreleased]\n- feat(a): a brand new thing\n\n## [0.0.1] - 2026-01-01\n- old thing\n')"
set +e
out="$(bash "$w/scripts/auto-bump.sh" --no-commit 2>&1)"; rc=$?
set -e
if [[ "$rc" != 0 ]]; then
  bad "unreleased-promotion" "exit $rc: $(tail -1 <<<"$out")"
elif ! grep -q '^## \[Unreleased\]$' "$w/CHANGELOG.md"; then
  bad "unreleased-promotion" "no [Unreleased] heading"
elif awk '/^## \[Unreleased\]/{f=1;next} /^## \[/{f=0} f && /^- /' "$w/CHANGELOG.md" | grep -q .; then
  bad "unreleased-promotion" "[Unreleased] is not empty after the bump"
elif ! awk '/^## \[0\.0\.2\]/{f=1;next} /^## \[/{f=0} f && /^- feat\(a\): a brand new thing$/' "$w/CHANGELOG.md" | grep -q .; then
  bad "unreleased-promotion" "entry did not move under the new version heading"
elif ! grep -q 'APP_VERSION: str = "0.0.2"' "$w/backend/app/core/config.py"; then
  bad "unreleased-promotion" "version not bumped"
else ok "unreleased-promotion" "$rc"; fi
rm -rf "$w"

# 5. Regression guard on the untouched path: an EMPTY [Unreleased] is not a
#    release, so the bot must leave CHANGELOG.md and the versions alone.
w="$(sandbox '## [Unreleased]\n\n## [0.0.1] - 2026-01-01\n- old thing\n')"
before="$(cat "$w/CHANGELOG.md")"
set +e
out="$(bash "$w/scripts/auto-bump.sh" --no-commit 2>&1)"; rc=$?
set -e
if [[ "$rc" != 0 ]]; then
  bad "empty-unreleased" "exit $rc: $(tail -1 <<<"$out")"
elif [[ "$out" != *"nothing to bump"* ]]; then
  bad "empty-unreleased" "expected 'nothing to bump', got: $(tail -1 <<<"$out")"
elif [[ "$(cat "$w/CHANGELOG.md")" != "$before" ]]; then
  bad "empty-unreleased" "CHANGELOG.md was modified"
elif ! grep -q 'APP_VERSION: str = "0.0.1"' "$w/backend/app/core/config.py"; then
  bad "empty-unreleased" "version was bumped without a release"
else ok "empty-unreleased" "$rc"; fi
rm -rf "$w"

[[ "$fail" == 0 ]] && echo "PASS: bump-version.sh survives an unset CARTO_API_KEY"
[[ "$fail" == 0 ]] && echo "PASS: auto-bump.sh promotes [Unreleased] and skips empty ones"
exit "$fail"
