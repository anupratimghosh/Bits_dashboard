#!/usr/bin/env bash
# Start the BITS Research Publication Analytics dashboard.
#   ./run.sh          production-style: one process, API + built UI on :8000
#   ./run.sh dev      two processes: API on :8000, Vite with hot reload on :5173
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r backend/requirements.txt
fi

if [ "${1:-}" = "dev" ]; then
  .venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8000 --reload &
  API=$!
  trap 'kill $API 2>/dev/null || true' EXIT
  cd frontend && npm run dev
else
  [ -d frontend/dist ] || (cd frontend && npm install && npm run build)
  exec .venv/bin/python -m uvicorn app.main:app --app-dir backend --port 8000
fi
