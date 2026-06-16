#!/bin/bash
# Launch wrapper for launchd. Loads .env, prevents sleep while running, and
# starts the dashboard + engine from the project's virtualenv.
set -euo pipefail

cd "$(cd "$(dirname "$0")/.." && pwd)"

# Load .env (KEY=VALUE lines) into the environment if present.
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    . ./.env
    set +a
fi

HOST="${PM_HOST:-0.0.0.0}"
PORT="${PM_PORT:-8000}"

# caffeinate -s keeps the Mac awake for as long as this process runs.
exec caffeinate -s ./.venv/bin/uvicorn backend.main:app --host "$HOST" --port "$PORT"
