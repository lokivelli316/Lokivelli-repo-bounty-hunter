#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_HOME="${LOKIVELLI_RADAR_HOME:-$HOME/lokivelli-radar}"
VENV="$APP_HOME/.venv"
printf '\n== Lokivelli Radar Termux installer ==\n'
pkg install -y python git termux-services curl
mkdir -p "$APP_HOME"
python -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV/bin/python" -m pip install -e "$ROOT"
"$VENV/bin/lokivelli-radar" --home "$APP_HOME" manuals >/dev/null
SERVICE_ROOT="$PREFIX/var/service"
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
sv up lokivelli-radar || true
sv up lokivelli-radar-scheduler || true
printf '\nGitHub token setup (local-only):\n  mkdir -p %s/config\n  printf %%s YOUR_TOKEN > %s/config/github_token\n  chmod 600 %s/config/github_token\n\n' "$APP_HOME" "$APP_HOME" "$APP_HOME"
printf 'Open: http://127.0.0.1:8765\n'
