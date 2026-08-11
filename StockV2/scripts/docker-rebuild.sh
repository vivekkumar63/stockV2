#!/usr/bin/env bash
# Full Docker rebuild (use after code changes)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "[docker] Stopping containers..."
docker compose down

echo "[docker] Rebuilding images (no cache)..."
docker compose build --no-cache

echo "[docker] Starting..."
docker compose up -d

echo "[docker] Waiting for health check..."
sleep 10
docker compose ps

echo ""
echo "App: http://localhost"
echo "API: http://localhost/health"
