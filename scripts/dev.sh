#!/usr/bin/env bash
# Start Autopilot on your computer:  ./scripts/dev.sh
# Needs Python 3.11+ (or uv), Node.js 18+ and Google Chrome. Nothing else: the database is a
# local file (data/autopilot.db). Ctrl+C stops everything.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)

say() { printf "\n\033[1m==> %s\033[0m\n" "$1"; }
fail() { printf "\n\033[31m%s\033[0m\n\n" "$1"; exit 1; }

# --- Check what's installed ----------------------------------------------------------
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PYTHON=$candidate
    break
  fi
done
if [ -z "$PYTHON" ] && ! command -v uv >/dev/null 2>&1; then
  fail "Python 3.11 or newer is needed. The easiest fix is to install uv (it fetches Python for you):
    curl -LsSf https://astral.sh/uv/install.sh | sh
then open a new terminal window and run ./scripts/dev.sh again."
fi
if ! command -v node >/dev/null 2>&1 ||
   ! node -e 'process.exit(parseInt(process.versions.node) >= 18 ? 0 : 1)' 2>/dev/null; then
  fail "Node.js 18 or newer is needed. Install it from https://nodejs.org (LTS) or with: brew install node"
fi
if [ "$(uname)" = "Darwin" ] && [ ! -d "/Applications/Google Chrome.app" ] && [ ! -d "$HOME/Applications/Google Chrome.app" ]; then
  echo "Note: Google Chrome wasn't found. The agent needs it to use websites (https://www.google.com/chrome)."
fi

if [ ! -f .env ]; then
  cp .env.example .env
fi
# Older .env files pointed at a Docker Postgres that is no longer used: switch them to the
# built-in local database.
if grep -q '^DATABASE_URL=postgresql+asyncpg://autopilot:autopilot@localhost:5433/autopilot' .env; then
  sed -i.bak 's|^DATABASE_URL=postgresql+asyncpg://autopilot:autopilot@localhost:5433/autopilot|# (old Docker setting, no longer needed) &|' .env
  rm -f .env.bak
  echo "Updated .env to use the built-in local database (Docker is no longer needed)."
fi
if ! grep -qE '^ANTHROPIC_API_KEY=.+' .env; then
  echo
  echo "Note: no ANTHROPIC_API_KEY in .env yet. The app will open, but the agent can't run until you"
  echo "add your key (https://console.anthropic.com) to .env and restart this script."
fi

# --- Install (first run only does real work) -------------------------------------------
say "Setting up the backend"
cd "$ROOT/backend"
if [ ! -x .venv/bin/python ]; then
  if [ -n "$PYTHON" ]; then "$PYTHON" -m venv .venv; else uv venv -q --python 3.12 .venv; fi
fi
if command -v uv >/dev/null 2>&1; then
  uv pip install -q --python .venv/bin/python -e .
else
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/python -m pip install -q -e .
fi
.venv/bin/alembic upgrade head

say "Setting up the web app"
cd "$ROOT/frontend"
[ -d node_modules ] || npm install --no-audit --no-fund

# --- Run --------------------------------------------------------------------------------
cd "$ROOT"
pids=()
cleanup() { echo; echo "Stopping..."; kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

(cd backend && .venv/bin/uvicorn app.main:app --port 8000) & pids+=($!)
(cd backend && .venv/bin/python -m app.worker) & pids+=($!)
(cd frontend && npm run dev) & pids+=($!)

say "Autopilot is running: open http://localhost:3000  (Ctrl+C to stop)"
wait
