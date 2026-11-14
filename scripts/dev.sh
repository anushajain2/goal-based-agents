#!/usr/bin/env bash
# Start everything locally: Postgres (Docker), migrations, API, agent worker and the web UI.
#   ./scripts/dev.sh
# Ctrl+C stops the API, worker and UI (Postgres keeps running; `docker compose down` stops it).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Add your ANTHROPIC_API_KEY to it, then run this again."
  exit 1
fi

echo "==> Postgres"
docker compose up -d --wait db

echo "==> Backend dependencies"
cd "$ROOT/backend"
if command -v uv >/dev/null 2>&1; then
  [ -d .venv ] || uv venv -q .venv
  uv pip install -q -e ".[dev]"
else
  [ -d .venv ] || python3 -m venv .venv
  .venv/bin/pip install -q -e ".[dev]"
fi
.venv/bin/alembic upgrade head

echo "==> Frontend dependencies"
cd "$ROOT/frontend"
[ -d node_modules ] || npm install --no-audit --no-fund

cd "$ROOT"
pids=()
cleanup() { echo; echo "Stopping..."; kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

(cd backend && .venv/bin/uvicorn app.main:app --port 8000 --reload) & pids+=($!)
(cd backend && .venv/bin/python -m app.worker) & pids+=($!)
(cd frontend && npm run dev) & pids+=($!)

echo
echo "Autopilot is starting: open http://localhost:3000"
wait
