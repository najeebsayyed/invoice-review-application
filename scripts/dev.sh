#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ "${1:-}" == "--check" ]]; then
  echo "Checking prerequisites..."
  [[ -f backend/.env ]] || { echo "backend/.env is missing." >&2; exit 1; }
  [[ -f frontend/.env ]] || { echo "frontend/.env is missing." >&2; exit 1; }
  echo "Invoice Review is ready to start."
  exit 0
fi

(
  cd backend
  uv run --locked --no-sync uvicorn app.main:create_app --factory --reload --port 8000
) &
(
  cd frontend
  pnpm dev
) &

trap 'kill 0' EXIT INT TERM
wait
