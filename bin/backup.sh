#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
APP_HOME="${LOKIVELLI_RADAR_HOME:-$HOME/lokivelli-radar}"
"$APP_HOME/.venv/bin/lokivelli-radar" --home "$APP_HOME" update backup
"$APP_HOME/.venv/bin/lokivelli-radar" --home "$APP_HOME" export
