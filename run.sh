#!/usr/bin/env bash
# Earshot — one command, no network required.
# Usage:  ./run.sh          then open http://127.0.0.1:8010
set -e
cd "$(dirname "$0")"

if [ ! -d backend/.venv ]; then
  echo "[setup] creating python env"
  (cd backend && uv venv --python 3.12 .venv && uv pip install fastapi "uvicorn[standard]")
fi

if [ ! -d frontend/dist ]; then
  echo "[setup] building the UI"
  (cd frontend && npm install && npm run build)
fi

cd backend
source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate
exec python -m uvicorn app:app --host 127.0.0.1 --port 8010
