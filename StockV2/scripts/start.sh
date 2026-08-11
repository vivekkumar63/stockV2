#!/usr/bin/env bash
# Start StockV2 (bare-metal, for development or manual restarts)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$SCRIPT_DIR/backend/.venv/bin"

# ── Backend ───────────────────────────────────────────────────────────────────
echo "[start] Starting backend on :8000 ..."
cd "$SCRIPT_DIR/backend"
"$VENV/uvicorn" main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "[start] Backend PID $BACKEND_PID"

# ── Frontend (dev only) ───────────────────────────────────────────────────────
if [[ "${1:-}" == "--dev" ]]; then
    echo "[start] Starting frontend dev server on :3000 ..."
    cd "$SCRIPT_DIR/frontend"
    npm run dev &
    FRONTEND_PID=$!
    echo "[start] Frontend PID $FRONTEND_PID"
    echo "$FRONTEND_PID" > /tmp/stockv2-frontend.pid
fi

echo "$BACKEND_PID" > /tmp/stockv2-backend.pid
echo "[start] Done. Logs: journalctl -u stockv2-backend -f  (or tail -f above)"
echo "        Stop with: ./scripts/stop.sh"
