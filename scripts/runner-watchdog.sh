#!/usr/bin/env bash
# runner-watchdog.sh — keeps the GitHub Actions self-hosted runner host responsive.
#
# Background (AUT-1720): the x64 runner's dockerd intermittently wedges during
# heavy `docker buildx build --push` publishes, leaving the publish job hung
# (the runner "frozen") until GitHub kills it with "context deadline exceeded".
# vm2 runners are not currently frozen, but the wedge is intermittent and
# unreleased, so we install proactive self-healing.
#
# Installed as a systemd timer (infra/systemd/gh-runner-watchdog.{service,timer}).
# Each tick:
#   1. probe dockerd (`docker info`) with a hard timeout;
#   2. act only after N consecutive failed probes (a slow multi-minute build is
#      NOT killed);
#   3. on sustained wedge: restart containerd + docker (the proven recovery),
#      then prune orphan buildx/builder state left by the wedged publish;
#   4. if a Runner.Listener is stuck in uninterruptible sleep (D state) and no
#      job is running, restart the offending gh-runner@ instance.
set -uo pipefail

: "${DOCKER_PROBE_TIMEOUT:=60}"   # seconds to wait for `docker info`
: "${DOCKER_PROBE_FAILS:=2}"      # consecutive fails before recovery (avoids slow builds)
: "${DOCKER_PRUNE:=yes}"          # prune orphan containers/cache after a dockerd restart
: "${STATE_DIR:=/home/administrator/.gh-runner-watchdog}"
: "${LOG_TAG:=gh-runner-watchdog}"

mkdir -p "$STATE_DIR/run" 2>/dev/null || true
exec 9>"$STATE_DIR/run/lock"; flock -n 9 || { log "another watchdog tick is running; skipping"; exit 0; } || true

# systemctl wrapper: the timer runs as a non-root service user, so escalate via
# sudo (a NOPASSWD sudoers drop-in authorises exactly docker/containerd/runner
# restarts). Falls back to plain systemctl when already root.
if [ "$(id -u)" -eq 0 ]; then sysctl() { systemctl "$@"; }; else sysctl() { sudo systemctl "$@"; }; fi

log() { logger -t "$LOG_TAG" -- "$*" 2>/dev/null || echo "$(date -u +%FT%TZ) $LOG_TAG: $*"; }

dockerd_responsive() { timeout "$DOCKER_PROBE_TIMEOUT" docker info >/dev/null 2>&1; }
runner_busy()        { pgrep -f 'Runner\.Worker' >/dev/null 2>&1; }
listener_pids()      { pgrep -f 'Runner\.Listener run' 2>/dev/null || true; }
listeners_in_dstate() {
  for p in $(listener_pids); do
    ps -o stat= -p "$p" 2>/dev/null | grep -q 'D' && echo "$p"
  done
}

incr_fail()  { local n; n=$(cat "$STATE_DIR/run/dockerf" 2>/dev/null || echo 0); n=$((n+1)); echo "$n" >"$STATE_DIR/run/dockerf"; echo "$n"; }
reset_fail() { echo 0 >"$STATE_DIR/run/dockerf" 2>/dev/null || true; }

restart_runner_slice() {
  # Restart failed gh-runner@ instances so a wedged Listener re-registers cleanly.
  # Safe to do only when no job is running (caller guarantees that).
  sysctl list-units --state=failed "gh-runner@*.service" --output json 2>/dev/null \
    | python3 -c "import sys,json;[print(u['unit']['name']) for u in json.load(sys.stdin)]" 2>/dev/null \
    | while read -r u; do [ -n "$u" ] && { log "restarting failed listener $u"; sysctl restart "$u"; }; done
}

recover_docker() {
  log "dockerd unresponsive after $DOCKER_PROBE_FAILS ticks; restarting containerd + docker"
  sysctl restart containerd.service 2>/dev/null || true
  sleep 3
  sysctl restart docker.service 2>/dev/null || true
  for _ in $(seq 1 90); do docker info >/dev/null 2>&1 && break; sleep 1; done
  if docker info >/dev/null 2>&1; then
    log "dockerd back up after restart"
    if [ "$DOCKER_PRUNE" = yes ]; then
      docker container prune -f >/dev/null 2>&1 || true
      docker buildx prune -f >/dev/null 2>&1 || true
      docker system prune -f --volumes >/dev/null 2>&1 || true
    fi
  else
    log "WARN: dockerd still down after restart attempt"
  fi
}

main() {
  log "tick: dockerd_responsive=$(dockerd_responsive && echo yes || echo no), runner_busy=$(runner_busy && echo yes || echo no)"
  if dockerd_responsive; then
    reset_fail
    if ! runner_busy; then
      if [ -n "$(listeners_in_dstate)" ]; then
        log "Runner.Listener in D state (frozen) and no job running; restarting listener"
        restart_runner_slice
      fi
    fi
  else
    local fails; fails=$(incr_fail)
    log "dockerd probe failed ($fails/$DOCKER_PROBE_FAILS)"
    if [ "$fails" -ge "$DOCKER_PROBE_FAILS" ]; then
      recover_docker
      reset_fail
    fi
  fi
}

case "${1:-run}" in
  run) main ;;
  selftest)
    echo "dockerd_responsive=$(dockerd_responsive && echo yes || echo no)"
    echo "runner_busy=$(runner_busy && echo yes || echo no)"
    echo "listener_pids=$(listener_pids)"
    echo "listeners_in_dstate=$(listeners_in_dstate)"
    echo "docker info probe (hard timeout ${DOCKER_PROBE_TIMEOUT}s):"
    t0=$(date +%s); if dockerd_responsive; then echo "responsive ok"; else echo "UNRESPONSIVE"; fi
    echo "  probe elapsed=$(( $(date +%s)-t0 ))s"
    ;;
  *) echo "usage: $0 [run|selftest]" >&2; exit 2 ;;
esac
