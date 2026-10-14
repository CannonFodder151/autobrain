#!/usr/bin/env bash
# Runnable self-check for the AUT-451 CI fixes. Extracts the real `run:` blocks
# from the workflow files and exercises their retry/skip logic with mocked
# git/gh binaries, so the test cannot drift from the workflows.
#
#   ./scripts/test-ci-fixes.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBLISH="$ROOT/.github/workflows/dockerhub-publish.yml"
SYNC="$ROOT/.github/workflows/sync-mobile.yml"

extract() {
  # $1=file $2=job $3=step-index -> print the run block
  python3 - "$1" "$2" "$3" <<'PYEOF'
import sys, yaml
d = yaml.safe_load(open(sys.argv[1]))
print(d['jobs'][sys.argv[2]]['steps'][int(sys.argv[3])]['run'])
PYEOF
}

W="$(mktemp -d)"
trap 'rm -rf "$W"' EXIT
cd "$W"
mkdir -p bin scripts
git init -q -b main .
git config user.name test && git config user.email test@test

cat > scripts/auto-bump.sh <<'EOF'
#!/usr/bin/env bash
echo "==> mock auto-bump"
EOF
chmod +x scripts/auto-bump.sh

cat > bin/git <<'EOF'
#!/usr/bin/env bash
# Per-invocation config, e.g. `git -c http.extraheader=... push` (AUT-5676).
while [ "${1:-}" = "-c" ]; do shift 2; done
case "$1" in
  push)
    n=0; [ -f counter ] && n="$(cat counter)"
    if [ "$n" -lt "${MAX_PUSH_FAILS:-0}" ]; then
      echo "$((n+1))" > counter
      echo "! [rejected] main -> main (non-fast-forward)" >&2
      exit 1
    fi
    echo "mock: push ok"
    exit 0;;
  pull)
    echo "mock: pull --rebase ok"
    exit 0;;
  tag)
    echo "mock: tag ok"
    exit 0;;
esac
exec /usr/bin/git "$@"
EOF
chmod +x bin/git

cat > bin/gh <<'EOF'
#!/usr/bin/env bash
n=0; [ -f ghcounter ] && n="$(cat ghcounter)"
if [ "$n" -lt "${GH_FAILS:-0}" ]; then
  echo "$((n+1))" > ghcounter
  echo "${GH_ERR:-HTTP 422: No ref found for: v1.2.3}" >&2
  exit 1
fi
echo "mock: workflow dispatched"
EOF
chmod +x bin/gh

cat > bin/sleep <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x bin/sleep

export PATH="$W/bin:$PATH"
# The extracted run blocks are the real workflow steps, run under `set -u`, so
# the secret the admin-push header is built from (AUT-5676) must be present.
export GH_PAT="test-pat-not-used-by-the-mock-git"
FAILURES=0
pass() { echo "  PASS"; }
fail() { echo "  FAIL: $*"; FAILURES=$((FAILURES+1)); }

# --- auto-bump: push rejected twice, succeeds on 3rd attempt ---
echo "==> auto-bump retry succeeds after transient rejections"
export MAX_PUSH_FAILS=2
extract "$PUBLISH" auto-bump 1 > run-auto-bump.sh
if (cd "$W" && bash run-auto-bump.sh) | grep -q 'auto-bump done'; then pass; else fail "expected success after 2 retries"; fi
rm -f counter

# --- auto-bump: push always rejected -> exits nonzero after 3 attempts ---
echo "==> auto-bump gives up after 3 attempts"
export MAX_PUSH_FAILS=99
if (cd "$W" && bash run-auto-bump.sh) >/dev/null 2>&1; then
  fail "expected nonzero exit after 3 attempts"
else
  pass
fi
unset MAX_PUSH_FAILS
rm -f counter

# --- changelog-gate: enforced on pull_request, skipped otherwise ---
echo "==> changelog-gate blocks app change without CHANGELOG.md on PR"
mkdir -p backend
echo "a" > backend/a.py && git add backend/a.py && git commit -qm base
BASE="$(git rev-parse HEAD)"
echo "b" > backend/b.py && git add backend/b.py && git commit -qm head-no-changelog
HEAD_BAD="$(git rev-parse HEAD)"
echo "c" > backend/c.py && echo "- c" > CHANGELOG.md && git add -A && git commit -qm head-with-changelog
HEAD_GOOD="$(git rev-parse HEAD)"

gate() { # $1=event $2=base_sha $3=head_sha
  GITHUB_SHA="$3" bash -c "$(extract "$PUBLISH" changelog-gate 1 \
    | sed -e "s|\${{ github.event_name }}|$1|g" \
          -e "s|\${{ github.event.pull_request.base.sha }}|$2|g")"
}

if gate pull_request "$BASE" "$HEAD_BAD" >/dev/null 2>&1; then
  fail "gate should reject app change without CHANGELOG.md"
else
  pass
fi
echo "==> changelog-gate passes when CHANGELOG.md included in PR"
if gate pull_request "$BASE" "$HEAD_GOOD" >/dev/null 2>&1; then pass; else fail "gate should pass with CHANGELOG.md"; fi
echo "==> changelog-gate skips on push (main handled by auto-bump)"
if gate push "$BASE" "$HEAD_BAD" >/dev/null 2>&1; then pass; else fail "gate should skip on push"; fi

# --- sync-mobile dispatch: 422 'No ref found' retried, then succeeds ---
echo "==> sync-mobile dispatch retries transient 422 'No ref found'"
extract "$SYNC" sync 4 | sed 's|\${{ steps.commit.outputs.version }}|1.2.3|g' > run-sync.sh
export GH_FAILS=2
if (cd "$W" && bash run-sync.sh) | grep -q 'dispatched mobile release v1.2.3'; then pass; else fail "expected dispatch success after 2 retries"; fi
rm -f ghcounter

# --- sync-mobile dispatch: persistent 422 -> nonzero exit after ~60s ---
echo "==> sync-mobile dispatch gives up on persistent 422"
export GH_FAILS=99
if (cd "$W" && bash run-sync.sh) >/dev/null 2>&1; then
  fail "expected nonzero exit after retries exhausted"
else
  pass
fi
unset GH_FAILS
rm -f ghcounter

# --- sync-mobile dispatch: non-consistency error fails fast ---
echo "==> sync-mobile dispatch fails fast on non-422 error"
export GH_FAILS=99 GH_ERR="HTTP 403: Permission denied"
if (cd "$W" && bash run-sync.sh) >/dev/null 2>&1; then
  fail "expected fail-fast on non-422 error"
else
  pass
fi

# --- auto-bump.sh: a stale vNEXT tag from a rejected push is re-pointed (AUT-5676) ---
# refs/tags/v0.3.312 pointed at a release commit whose main push was rejected
# with GH006, so every later run logged "tag already exists — skipping" over a
# commit that never reached main. Run the real auto-bump.sh against a fixture
# repo; REAL_PATH drops the mocked git so the tag/commit plumbing is genuine.
REAL_PATH="${PATH#$W/bin:}"

fixture() { # $1=dir $2=new version
  mkdir -p "$1/scripts" "$1/backend/app/core"
  git -C "$1" init -q -b main
  git -C "$1" config user.name t && git -C "$1" config user.email t@t
  printf 'APP_VERSION: str = "0.3.311"\n' > "$1/backend/app/core/config.py"
  printf '# Changelog\n\n## [Unreleased]\n\n- something worth shipping\n' > "$1/CHANGELOG.md"
  # mock of the version rewriter — the real one also touches ai/ and frontend/
  printf '#!/usr/bin/env bash\nsed -i "s/0\\.3\\.311/%s/" backend/app/core/config.py\n' "$2" \
    > "$1/scripts/bump-version.sh"
  chmod +x "$1/scripts/bump-version.sh"
  cp "$ROOT/scripts/auto-bump.sh" "$1/scripts/auto-bump.sh"
  git -C "$1" add -A && git -C "$1" commit -qm base
}

echo "==> auto-bump.sh re-points a stale tag whose commit is not on main"
STALE="$W/stale"; fixture "$STALE" 0.3.312
# debris: tag an empty commit, then take it back off main (as GH006 did)
git -C "$STALE" commit -q --allow-empty -m orphan
git -C "$STALE" tag -a v0.3.312 -m debris
git -C "$STALE" reset -q --hard HEAD~1
OUT="$( cd "$STALE" && PATH="$REAL_PATH" bash scripts/auto-bump.sh 2>&1 )" || true
case "$OUT" in
  *"not on main"*) pass ;;
  *) fail "expected the stale v0.3.312 tag to be re-pointed, got: $OUT" ;;
esac
if [ "$(git -C "$STALE" rev-parse 'v0.3.312^{commit}')" = "$(git -C "$STALE" rev-parse HEAD)" ]; then
  pass
else
  fail "v0.3.312 still points off main: $(git -C "$STALE" rev-parse --short 'v0.3.312^{commit}')"
fi
case "$(git -C "$STALE" log -1 --format=%s)" in
  *"release v0.3.312"*"[skip ci]"*) pass ;;
  *) fail "release commit lost its [skip ci] marker: $(git -C "$STALE" log -1 --format=%s)" ;;
esac

echo "==> auto-bump.sh leaves a tag that is already on main alone"
LANDED="$W/landed"; fixture "$LANDED" 0.3.312
git -C "$LANDED" tag -a v0.3.312 -m released
OUT="$( cd "$LANDED" && PATH="$REAL_PATH" bash scripts/auto-bump.sh 2>&1 )" || true
case "$OUT" in
  *"tag v0.3.312 already exists — skipping"*) pass ;;
  *) fail "expected the on-main tag to be left alone, got: $OUT" ;;
esac

if [ "$FAILURES" -gt 0 ]; then
  echo "==> $FAILURES check(s) failed"
  exit 1
fi
echo "==> all checks passed"
