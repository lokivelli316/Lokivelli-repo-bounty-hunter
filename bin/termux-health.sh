#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_HOME="${LOKIVELLI_RADAR_HOME:-$HOME/lokivelli-radar}"
export SVDIR="$PREFIX/var/service"
export LOGDIR="$PREFIX/var/log"
printf 'APP_HOME=%s\n' "$APP_HOME"
command -v python >/dev/null && python --version || true
command -v git >/dev/null && git --version || true

if curl -fsS http://127.0.0.1:8765/healthz >"$APP_HOME/var/healthz-readback.json" 2>/dev/null; then
  echo 'HTTP_SERVICE=LIVE'
else
  echo 'HTTP_SERVICE=HOLD'
fi

if curl -fsS http://127.0.0.1:8765/api/dashboard >"$APP_HOME/var/dashboard-readback.json" 2>/dev/null; then
  echo 'DASHBOARD_READBACK=LIVE'
else
  echo 'DASHBOARD_READBACK=HOLD'
fi

if command -v sv >/dev/null 2>&1; then
  sv status "$SVDIR/lokivelli-radar" 2>/dev/null || true
  sv status "$SVDIR/lokivelli-radar-scheduler" 2>/dev/null || true
fi

for pf in "$APP_HOME/var/http-install-fallback.pid" "$APP_HOME/var/scheduler-install-fallback.pid" "$APP_HOME/var/http-start-fallback.pid" "$APP_HOME/var/scheduler-start-fallback.pid"; do
  if [ -s "$pf" ] && kill -0 "$(cat "$pf")" 2>/dev/null; then
    printf 'FALLBACK_PROCESS=RUNNING pid=%s file=%s\n' "$(cat "$pf")" "$pf"
  fi
done
