#!/bin/bash
# One-command macOS install: venv + deps + launchd service.
# Re-run after pulling new code to reload the service.
set -euo pipefail

APPDIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_SRC="$APPDIR/deploy/com.polymarket-arb.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.polymarket-arb.plist"

echo "==> Project: $APPDIR"

# 1. virtualenv + dependencies (incl. live extras)
if [ ! -d "$APPDIR/.venv" ]; then
    echo "==> Creating virtualenv"
    python3 -m venv "$APPDIR/.venv"
fi
echo "==> Installing dependencies"
"$APPDIR/.venv/bin/pip" install -q -U pip
"$APPDIR/.venv/bin/pip" install -q -r "$APPDIR/requirements.txt"
"$APPDIR/.venv/bin/pip" install -q py-clob-client websockets || \
    echo "    (py-clob-client optional — needed only for live execution)"

mkdir -p "$APPDIR/logs"
chmod +x "$APPDIR/deploy/run.sh"

# 2. .env scaffold
if [ ! -f "$APPDIR/.env" ]; then
    cp "$APPDIR/.env.example" "$APPDIR/.env"
    echo "==> Created .env from template — EDIT IT before going live."
fi

# 3. template the launchd plist with the absolute project path
echo "==> Installing launchd agent -> $PLIST_DST"
mkdir -p "$HOME/Library/LaunchAgents"
sed "s#__APPDIR__#$APPDIR#g" "$PLIST_SRC" > "$PLIST_DST"

# 4. (re)load the service
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"

echo ""
echo "==> Done. The bot is running as com.polymarket-arb."
echo "    Dashboard: http://localhost:8000"
echo "    Logs:      $APPDIR/logs/arb.out.log"
echo ""
echo "    Keep the Mac awake:  sudo pmset -a sleep 0 disablesleep 1"
echo "    Stop the service:    launchctl unload $PLIST_DST"
