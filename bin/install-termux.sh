#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_HOME="${LOKIVELLI_RADAR_HOME:-$HOME/lokivelli-radar}"
VENV="$APP_HOME/.venv"
SERVICE_ROOT="$PREFIX/var/service"
HEALTH_URL="http://127.0.0.1:8765/healthz"
DASHBOARD_URL="http://127.0.0.1:8765/api/dashboard"

printf '\n== Lokivelli Radar Termux installer ==\n'
pkg install -y python git termux-services curl
export SVDIR="$PREFIX/var/service"
export LOGDIR="$PREFIX/var/log"
if [ -f "$PREFIX/etc/profile.d/start-services.sh" ]; then
  # Same-session installs do not get the profile hook until the next shell.
  # Source it now so runit has the same environment Termux documents.
  . "$PREFIX/etc/profile.d/start-services.sh"
fi
mkdir -p "$APP_HOME" "$APP_HOME/logs" "$APP_HOME/var"

python -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV/bin/python" -m pip install -e "$ROOT" pytest
"$VENV/bin/lokivelli-radar" --home "$APP_HOME" manuals >"$APP_HOME/var/install-manuals.json"

mkdir -p "$SERVICE_ROOT/lokivelli-radar" "$SERVICE_ROOT/lokivelli-radar-scheduler"
cat > "$SERVICE_ROOT/lokivelli-radar/run" <<RUN
#!/data/data/com.termux/files/usr/bin/sh
exec 2>&1
export LOKIVELLI_RADAR_HOME="$APP_HOME"
exec "$VENV/bin/lokivelli-radar" --home "$APP_HOME" serve
RUN
cat > "$SERVICE_ROOT/lokivelli-radar-scheduler/run" <<RUN
#!/data/data/com.termux/files/usr/bin/sh
exec 2>&1
export LOKIVELLI_RADAR_HOME="$APP_HOME"
exec "$VENV/bin/lokivelli-radar" --home "$APP_HOME" scheduler
RUN
chmod +x "$SERVICE_ROOT/lokivelli-radar/run" "$SERVICE_ROOT/lokivelli-radar-scheduler/run"

"$VENV/bin/lokivelli-radar" --home "$APP_HOME" register-runtime "$ROOT"   --port 8765   --health "$HEALTH_URL"   --service-name lokivelli-radar >"$APP_HOME/var/install-register-runtime.json"

sv-enable lokivelli-radar >/dev/null 2>&1 || true
sv-enable lokivelli-radar-scheduler >/dev/null 2>&1 || true
sv up "$SVDIR/lokivelli-radar" >/dev/null 2>&1 || true
sv up "$SVDIR/lokivelli-radar-scheduler" >/dev/null 2>&1 || true

for _ in $(seq 1 12); do
  if curl -fsS "$HEALTH_URL" >"$APP_HOME/var/install-health.json" 2>/dev/null; then
    break
  fi
  sleep 1
done

if ! curl -fsS "$HEALTH_URL" >"$APP_HOME/var/install-health.json" 2>/dev/null; then
  printf 'runit health did not come LIVE; starting verified local-process workaround\n'
  nohup "$VENV/bin/lokivelli-radar" --home "$APP_HOME" serve     >"$APP_HOME/logs/http-install-fallback.log" 2>&1 &
  echo $! >"$APP_HOME/var/http-install-fallback.pid"
  nohup "$VENV/bin/lokivelli-radar" --home "$APP_HOME" scheduler     >"$APP_HOME/logs/scheduler-install-fallback.log" 2>&1 &
  echo $! >"$APP_HOME/var/scheduler-install-fallback.pid"
  for _ in $(seq 1 12); do
    if curl -fsS "$HEALTH_URL" >"$APP_HOME/var/install-health.json" 2>/dev/null; then
      break
    fi
    sleep 1
  done
fi

if ! curl -fsS "$HEALTH_URL" >"$APP_HOME/var/install-health.json"; then
  printf 'HOLD: local HTTP health did not verify at %s\n' "$HEALTH_URL" >&2
  exit 1
fi

curl -fsS "$DASHBOARD_URL" >"$APP_HOME/var/install-dashboard-readback.json"
"$VENV/bin/lokivelli-radar" --home "$APP_HOME" discover >"$APP_HOME/var/install-discovery.json"
"$VENV/bin/lokivelli-radar" --home "$APP_HOME" runtime-transition "$ROOT" VERIFYING   --operation "install:health+dashboard+export" >"$APP_HOME/var/install-runtime-verifying.json"
"$VENV/bin/lokivelli-radar" --home "$APP_HOME" export >"$APP_HOME/var/install-export.json"
"$VENV/bin/lokivelli-radar" --home "$APP_HOME" runtime-transition "$ROOT" LIVE   --operation "install:healthz+dashboard-readback+export" >"$APP_HOME/var/install-runtime-live.json"

printf '\nLOCAL SERVICE RUNTIME=LIVE\n'
printf 'Health: %s\n' "$HEALTH_URL"
printf 'GUI:    http://127.0.0.1:8765\n'
printf 'Evidence: %s/var/install-*.json\n' "$APP_HOME"
printf '\nGitHub authentication remains a separate acceptance gate.\n'
printf 'Local-only token file, if needed:\n'
printf '  mkdir -p %s/config\n' "$APP_HOME"
printf '  printf %%s YOUR_TOKEN > %s/config/github_token\n' "$APP_HOME"
printf '  chmod 600 %s/config/github_token\n' "$APP_HOME"
printf '\nAfter authentication, run:\n'
printf '  %s/bin/lokivelli-radar --home %s acceptance --source-dir %s\n\n' "$VENV" "$APP_HOME" "$ROOT"
