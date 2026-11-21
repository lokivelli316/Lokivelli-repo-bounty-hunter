#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
APP_HOME="${LOKIVELLI_RADAR_HOME:-$HOME/lokivelli-radar}"
VENV="$APP_HOME/.venv"
if command -v sv >/dev/null 2>&1; then sv up lokivelli-radar || true; fi
if command -v termux-open-url >/dev/null 2>&1; then termux-open-url "http://127.0.0.1:8765"; else "$VENV/bin/lokivelli-radar" --home "$APP_HOME" serve; fi
