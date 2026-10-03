#!/usr/bin/env bash
# AUT-5134: hosted stack health watchdog.
#
# The gap that turned a 1-minute host typo into a 16-minute outage: a
# hosted container whose RestartCount grew (or that left
# `running (healthy)`) said nothing. This poll posts one embed to
# Discord through the n8n Reporter.
#
# Events:
#   * RestartCount grows          -> #incidents
#   * running but not healthy     -> #ops
#   * left the running state      -> #incidents
#   * healthy / running again     -> #incidents (resolved colour)
# Every event is latched in a state file, so a fault is reported once
# and its recovery once — the timer can poll forever without spamming.
#
# Install on the host:
#   install -m 0755 scripts/hosted-health-watch.sh /usr/local/bin/
#   install -m 0644 infra/systemd/autobrain-health-watch.{service,timer} \
#       /etc/systemd/system/
#   systemctl daemon-reload && systemctl enable --now autobrain-health-watch.timer
set -uo pipefail

: "${DOCKER:=docker}"
: "${CURL:=curl}"
: "${DISCORD_REPORT_URL:=https://n8n.nathanmartina.com/webhook/discord-report}"
: "${PROJECT:=autobrain-hosted}"
: "${STATE_DIR:=/var/lib/autobrain-health-watch}"
: "${START_GRACE_SECS:=180}"
: "${REPORT_AUTHOR:=Health Watchdog}"
: "${WEBHOOK_TIMEOUT:=10}"

mkdir -p "$STATE_DIR" || exit 1
STATE="$STATE_DIR/state"
LOCK="$STATE_DIR/lock"
# flock keeps overlapping timer runs from double-reporting the same event.
exec 9>"$LOCK" || exit 1
flock -n 9 || exit 0

log() { echo "$(date -u +%FT%TZ) health-watch: $*"; }

json_str() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g'; }

# notify <channel> <colour> <title> <description> [field=value ...]
notify() {
    local channel=$1 color=$2 title=$3 description=$4
    shift 4
    local fields="" f name value
    for f in "$@"; do
        name=${f%%=*}
        value=${f#*=}
        fields="$fields{\"name\":\"$(json_str "$name")\",\"value\":\"$(json_str "$value")\",\"inline\":true},"
    done
    fields=${fields%,}
    local payload
    payload=$(printf '{"channel":"%s","title":"%s","description":"%s","color":"%s","author":"%s","fields":[%s]}' \
        "$(json_str "$channel")" "$(json_str "$title")" "$(json_str "$description")" \
        "$color" "$(json_str "$REPORT_AUTHOR")" "$fields")
    if ! $CURL -sS --max-time "$WEBHOOK_TIMEOUT" -X POST "$DISCORD_REPORT_URL" \
        -H 'Content-Type: application/json' -d "$payload" >/dev/null; then
        log "WARN report post failed (${channel})"
    fi
}

[ -f "$STATE" ] || : >"$STATE"

declare -A S_RESTARTS S_HEALTH S_FAULT S_FIRST
while read -r n r h f t; do
    [ -n "$n" ] || continue
    S_RESTARTS[$n]=$r
    S_HEALTH[$n]=$h
    S_FAULT[$n]=$f
    S_FIRST[$n]=$t
done <"$STATE"

now=$(date +%s)
NEXT="$STATE_DIR/next"
: >"$NEXT"
changed=0

names=$($DOCKER ps -a --filter "label=com.docker.compose.project=$PROJECT" \
    --format '{{.Names}}' 2>/dev/null)
[ -n "$names" ] || { log "no containers for project ${PROJECT}"; exit 0; }

while IFS='|' read -r cname restarts cstatus chealth crunning; do
    [ -n "$cname" ] || continue
    cname=${cname#/}
    printf '%s %s %s\n' "$cname" "$restarts" "$chealth" >>"$NEXT.meta"

    known=0
    [ -n "${S_RESTARTS[$cname]+x}" ] && known=1
    prev_restarts=${S_RESTARTS[$cname]:-0}
    prev_fault=${S_FAULT[$cname]:-0}
    first=${S_FIRST[$cname]:-$now}

    if [ "$known" = 0 ]; then
        # First sighting: adopt as the baseline, report nothing.
        printf '%s %s %s %s %s\n' "$cname" "$restarts" "$chealth" 0 "$now" >>"$NEXT"
        continue
    fi

    if [ "$restarts" -gt "$prev_restarts" ]; then
        delta=$((restarts - prev_restarts))
        first=$now
        log "${cname}: RestartCount ${prev_restarts} -> ${restarts}"
        notify incidents 0xED4245 \
            "Restarted: ${cname} (${PROJECT})" \
            "RestartCount grew by ${delta} — crash-looping or killed. \`docker logs ${cname} --tail 50\` for the reason." \
            "Status=${cstatus}" "Restarts=${restarts}" "Project=${PROJECT}"
        changed=1
    fi

    if [ "$crunning" != "true" ]; then
        if [ "$prev_fault" != "2" ]; then
            log "${cname}: left running state (${cstatus})"
            notify incidents 0xED4245 \
                "Not running: ${cname} (${PROJECT})" \
                "Container is no longer running. \`docker logs ${cname} --tail 50\` for the reason." \
                "State=${cstatus}" "Restarts=${restarts}" "Project=${PROJECT}"
            changed=1
        fi
        printf '%s %s %s %s %s\n' "$cname" "$restarts" "$chealth" 2 "$now" >>"$NEXT"
        continue
    fi

    # Running. A container with no healthcheck has no health signal:
    # RestartCount + running state is its whole story.
    if [ "$chealth" = "none" ]; then
        if [ "$prev_fault" != "0" ]; then
            log "${cname}: running again"
            notify incidents 0xE67E22 \
                "Recovered: ${cname} (${PROJECT})" \
                "Running again (no healthcheck configured), restarts at ${restarts}." \
                "Restarts=${restarts}" "Project=${PROJECT}"
            changed=1
        fi
        printf '%s %s %s %s %s\n' "$cname" "$restarts" "$chealth" 0 "$now" >>"$NEXT"
        continue
    fi

    if [ "$chealth" = "healthy" ]; then
        if [ "$prev_fault" != "0" ]; then
            log "${cname}: healthy again"
            notify incidents 0xE67E22 \
                "Recovered: ${cname} (${PROJECT})" \
                "Back to running (healthy), restarts at ${restarts}." \
                "Restarts=${restarts}" "Project=${PROJECT}"
            changed=1
        fi
        printf '%s %s %s %s %s\n' "$cname" "$restarts" "$chealth" 0 "$now" >>"$NEXT"
        continue
    fi

    # Running but not healthy. `starting` is only a fault once the
    # start grace window has elapsed without resolving.
    if [ "$chealth" = "starting" ] && [ $((now - first)) -lt "$START_GRACE_SECS" ]; then
        printf '%s %s %s %s %s\n' "$cname" "$restarts" "$chealth" "$prev_fault" "$first" >>"$NEXT"
        continue
    fi
    if [ "$prev_fault" != "1" ]; then
        log "${cname}: left running (healthy) -> ${chealth}"
        notify ops 0xED4245 \
            "Unhealthy: ${cname} (${PROJECT})" \
            "Healthcheck is '${chealth}', not 'healthy'. Container is up but failing — no restart has happened yet." \
            "Health=${chealth}" "Status=${cstatus}" "Restarts=${restarts}"
        changed=1
    fi
    printf '%s %s %s %s %s\n' "$cname" "$restarts" "$chealth" 1 "$first" >>"$NEXT"
done < <($DOCKER inspect --format '{{.Name}}|{{.RestartCount}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|{{.State.Running}}' \
    $names 2>/dev/null)

mv "$NEXT" "$STATE"
rm -f "$NEXT.meta"
[ "$changed" = 1 ] || log "no events"
exit 0