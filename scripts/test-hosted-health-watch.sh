#!/usr/bin/env bash
# AUT-5134: self-check for scripts/hosted-health-watch.sh.
# Run: bash scripts/test-hosted-health-watch.sh
# No docker daemon and no network: $DOCKER and $CURL point at stubs
# that read a fixture and capture every webhook payload. Counts are
# cumulative — a latched event must never be reposted.
set -uo pipefail

WATCH="$(dirname "$0")/hosted-health-watch.sh"
DIR=$(mktemp -d)
trap 'rm -rf "$DIR"' EXIT
fails=0

fail() { echo "FAIL: $1"; fails=$((fails + 1)); }
pass() { echo "ok: $1"; }

cat >"$DIR/docker" <<'STUB'
#!/usr/bin/env bash
if [ "$1" = "ps" ]; then
    while IFS='|' read -r n _; do [ -n "$n" ] && echo "/$n"; done <"$FAKE_DOCKER_STATE"
else
    cat "$FAKE_DOCKER_STATE"
fi
STUB
cat >"$DIR/curl" <<'STUB'
#!/usr/bin/env bash
prev=""
for a in "$@"; do
    [ "$prev" = "-d" ] && printf '%s\n' "$a" >>"$FAKE_CURL_LOG"
    prev="$a"
done
STUB
chmod +x "$DIR/docker" "$DIR/curl"

: >"$DIR/posts.jsonl"
fixture() { printf '%s\n' "$1" >"$DIR/state.txt"; }
posts() { wc -l <"$DIR/posts.jsonl" 2>/dev/null || echo 0; }
run_watch() {
    env DOCKER="$DIR/docker" CURL="$DIR/curl" \
        DISCORD_REPORT_URL="http://reporter.invalid/hook" \
        PROJECT="autobrain-hosted" STATE_DIR="$DIR/watch" \
        START_GRACE_SECS=180 FAKE_DOCKER_STATE="$DIR/state.txt" \
        FAKE_CURL_LOG="$DIR/posts.jsonl" bash "$WATCH" >/dev/null 2>&1
}
# channel/title of the most recent payload
last() { python3 - "$DIR/posts.jsonl" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
r = rows[-1] if rows else {}
print(r.get("channel", "-"), "|", r.get("title", "-"))
PY
}
expect() { # expect <count> <channel> <title-substring>
    local want=$1 chan=$2 title=$3 got
    got=$(last)
    if [ "$(posts)" = "$want" ]; then pass "$title posts report #$want";
    else fail "$title posted $(posts), want $want"; fi
    case "$got" in "$chan |"*) pass "$title goes to #$chan";; *) fail "$title channel was: $got";; esac
    case "$got" in *"$title"*) pass "$title names the event";; *) fail "$title title was: $got";; esac
}

# 1. healthy baseline: adopt silently, report nothing
fixture 'backend|0|Up 4 minutes|healthy|true
postgres|0|Up 4 minutes|healthy|true'
run_watch
if [ "$(posts)" = 0 ]; then pass "healthy baseline reports nothing"; else fail "baseline posted $(posts)"; fi

# 2. RestartCount grows -> one #incidents embed
fixture 'backend|1|Up 12 seconds (health: starting)|starting|true
postgres|0|Up 4 minutes|healthy|true'
run_watch
expect 1 incidents Restarted

# 3. same restart count again: latched, no repeat
run_watch
if [ "$(posts)" = 1 ]; then pass "unchanged restart count does not repost"; else fail "repeat run reposted ($(posts))"; fi

# 4. leaves running (healthy) while still up -> #ops
fixture 'backend|1|Up 3 minutes|unhealthy|true
postgres|0|Up 4 minutes|healthy|true'
run_watch
expect 2 ops Unhealthy

# 5. recovery -> one resolved-colour embed
fixture 'backend|1|Up 30 minutes|healthy|true
postgres|0|Up 4 minutes|healthy|true'
run_watch
expect 3 incidents Recovered

# 6. container leaves the running state -> #incidents
fixture 'backend|1|Exited (1) 40 seconds ago|none|false
postgres|0|Up 4 minutes|healthy|true'
run_watch
expect 4 incidents Not

# 7. every payload is a Reporter-shaped embed
if python3 - "$DIR/posts.jsonl" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
assert len(rows) == 4, f"expected 4 captured payloads, got {len(rows)}"
for r in rows:
    assert r["channel"] in {"ops", "incidents"}, r["channel"]
    assert len(r["title"]) <= 90, r["title"]
    assert r["description"], r["title"]
    assert 1 <= len(r["fields"]) <= 4, r["fields"]
    assert all(f.get("inline") is True for f in r["fields"])
    assert r["color"].startswith("0x"), r["color"]
PY
then pass "all payloads are Reporter-shaped embeds"; else fail "payload shape check failed"; fi

# 8. no containers for the project: clean no-op
fixture ''
run_watch
if [ "$(posts)" = 4 ]; then pass "empty project list is a no-op"; else fail "empty project list posted $(posts)"; fi

if [ "$fails" = 0 ]; then echo "OK: hosted-health-watch.sh"; else echo "$fails failure(s)"; exit 1; fi