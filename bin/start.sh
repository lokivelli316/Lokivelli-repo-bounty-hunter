#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

APP_HOME="${LOKIVELLI_RADAR_HOME:-$HOME/lokivelli-radar}"
VENV="$APP_HOME/.venv"
HEALTH_URL="http://127.0.0.1:8765/healthz"
export SVDIR="$PREFIX/var/service"
export LOGDIR="$PREFIX/var/log"

mkdir -p "$APP_HOME/logs" "$APP_HOME/var"

if command -v sv >/dev/null 2>&1; then
  sv up "$SVDIR/lokivelli-radar" >/dev/null 2>&1 || true
  sv up "$SVDIR/lokivelli-radar-scheduler" >/dev/null 2>&1 || true
fi

for _ in $(seq 1 5); do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
  nohup "$VENV/bin/lokivelli-radar" --home "$APP_HOME" serve     >"$APP_HOME/logs/http-start-fallback.log" 2>&1 &
  echo $! >"$APP_HOME/var/http-start-fallback.pid"
  nohup "$VENV/bin/lokivelli-radar" --home "$APP_HOME" scheduler     >"$APP_HOME/logs/scheduler-start-fallback.log" 2>&1 &
  echo $! >"$APP_HOME/var/scheduler-start-fallback.pid"
  for _ in $(seq 1 8); do
    if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

if ! curl -fsS "$HEALTH_URL" >"$APP_HOME/var/start-health.json"; then
  printf 'HOLD: Repo Bounty Hunter did not reach HTTP health at %s\n' "$HEALTH_URL" >&2
  exit 1
fi

printf 'HTTP_SERVICE=LIVE\n'
if command -v termux-open-url >/dev/null 2>&1; then
  termux-open-url "http://127.0.0.1:8765"
else
  printf 'Open http://127.0.0.1:8765\n'
fi
