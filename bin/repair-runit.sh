#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_HOME="${LOKIVELLI_RADAR_HOME:-$HOME/lokivelli-radar}"
VENV="$APP_HOME/.venv"
SVDIR="${SVDIR:-$PREFIX/var/service}"
LOGDIR="${LOGDIR:-$PREFIX/var/log}"
export SVDIR LOGDIR

HTTP_SERVICE="$SVDIR/lokivelli-radar"
SCHED_SERVICE="$SVDIR/lokivelli-radar-scheduler"
HEALTH_URL="http://127.0.0.1:8765/healthz"

mkdir -p "$APP_HOME/logs" "$APP_HOME/var"

if [ ! -x "$HTTP_SERVICE/run" ] || [ ! -x "$SCHED_SERVICE/run" ]; then
  echo "HOLD: runit service definitions are missing; rerun bin/install-termux.sh" >&2
  exit 1
fi

if [ -f "$PREFIX/etc/profile.d/start-services.sh" ]; then
  . "$PREFIX/etc/profile.d/start-services.sh"
else
  service-daemon start >/dev/null 2>&1 || true
fi

for _ in $(seq 1 10); do
  if [ -d "$HTTP_SERVICE/supervise" ] && [ -d "$SCHED_SERVICE/supervise" ]; then
    break
  fi
  sleep 1
done

if [ ! -d "$HTTP_SERVICE/supervise" ] || [ ! -d "$SCHED_SERVICE/supervise" ]; then
  echo "HOLD: service-daemon did not attach supervise directories; verified fallback remains untouched" >&2
  exit 1
fi

sv-enable lokivelli-radar >/dev/null 2>&1 || true
sv-enable lokivelli-radar-scheduler >/dev/null 2>&1 || true
sv up "$HTTP_SERVICE" >/dev/null 2>&1 || true
sv up "$SCHED_SERVICE" >/dev/null 2>&1 || true

stop_fallback_pid() {
  local pf="$1"
  [ -s "$pf" ] || return 0
  local pid
  pid="$(cat "$pf" 2>/dev/null || true)"
  [ -n "$pid" ] || return 0
  if kill -0 "$pid" 2>/dev/null; then
    local cmd
    cmd="$(ps -p "$pid" -o args= 2>/dev/null || true)"
    case "$cmd" in
      *lokivelli-radar*)
        kill "$pid" 2>/dev/null || true
        for _ in $(seq 1 10); do
          kill -0 "$pid" 2>/dev/null || break
          sleep 0.2
        done
        ;;
      *)
        echo "HOLD: refusing to kill PID $pid because command line does not identify lokivelli-radar: $cmd" >&2
        exit 1
        ;;
    esac
  fi
  rm -f "$pf"
}

# Only remove the workaround after runit supervision itself exists.
stop_fallback_pid "$APP_HOME/var/http-install-fallback.pid"
stop_fallback_pid "$APP_HOME/var/scheduler-install-fallback.pid"
stop_fallback_pid "$APP_HOME/var/http-start-fallback.pid"
stop_fallback_pid "$APP_HOME/var/scheduler-start-fallback.pid"

sv restart "$HTTP_SERVICE" >/dev/null 2>&1 || true
sv restart "$SCHED_SERVICE" >/dev/null 2>&1 || true

for _ in $(seq 1 15); do
  if curl -fsS "$HEALTH_URL" >"$APP_HOME/var/runit-repair-health.json" 2>/dev/null; then
    break
  fi
  sleep 1
done

HTTP_STATUS="$(sv status "$HTTP_SERVICE" 2>&1 || true)"
SCHED_STATUS="$(sv status "$SCHED_SERVICE" 2>&1 || true)"
printf '%s\n' "$HTTP_STATUS" >"$APP_HOME/var/runit-http-status.txt"
printf '%s\n' "$SCHED_STATUS" >"$APP_HOME/var/runit-scheduler-status.txt"

if curl -fsS "$HEALTH_URL" >/dev/null 2>&1   && printf '%s' "$HTTP_STATUS" | grep -q '^run:'   && printf '%s' "$SCHED_STATUS" | grep -q '^run:'; then
  "$VENV/bin/lokivelli-radar" --home "$APP_HOME" discover >"$APP_HOME/var/runit-repair-discovery.json"
  echo "RUNIT_HTTP=LIVE"
  echo "RUNIT_SCHEDULER=LIVE"
  echo "HTTP_SERVICE=LIVE"
  echo "$HTTP_STATUS"
  echo "$SCHED_STATUS"
  exit 0
fi

echo "HOLD: runit takeover did not verify; restoring local-process workaround" >&2
nohup "$VENV/bin/lokivelli-radar" --home "$APP_HOME" serve   >"$APP_HOME/logs/http-repair-fallback.log" 2>&1 &
echo $! >"$APP_HOME/var/http-start-fallback.pid"
nohup "$VENV/bin/lokivelli-radar" --home "$APP_HOME" scheduler   >"$APP_HOME/logs/scheduler-repair-fallback.log" 2>&1 &
echo $! >"$APP_HOME/var/scheduler-start-fallback.pid"

for _ in $(seq 1 10); do
  curl -fsS "$HEALTH_URL" >/dev/null 2>&1 && break
  sleep 1
done

curl -fsS "$HEALTH_URL" >/dev/null 2>&1 && echo "FALLBACK_SERVICE=LIVE"
exit 1
