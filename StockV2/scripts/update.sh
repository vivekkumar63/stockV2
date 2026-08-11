#!/usr/bin/env bash
# Pull latest code and rebuild without losing data
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_USER="${STOCKV2_USER:-stockv2}"
VENV="$SCRIPT_DIR/backend/.venv/bin"

echo "[update] Pulling latest code..."
git -C "$SCRIPT_DIR" pull --rebase

echo "[update] Installing/updating Python dependencies..."
cd "$SCRIPT_DIR/backend"
"$VENV/poetry" install --only main --no-interaction 2>/dev/null || \
    /usr/local/bin/poetry install --only main --no-interaction

echo "[update] Rebuilding frontend..."
cd "$SCRIPT_DIR/frontend"
npm ci
npm run build

echo "[update] Restarting backend service..."
if systemctl is-active --quiet stockv2-backend; then
    systemctl restart stockv2-backend
    echo "[update] Backend restarted."
else
    echo "[update] systemd service not running — start with: systemctl start stockv2-backend"
fi

echo "[update] Reloading nginx..."
systemctl reload nginx

echo "[update] Done."
