#!/usr/bin/env bash
# Stop StockV2 (bare-metal manual mode)
set -euo pipefail

stop_pid() {
    local pidfile="$1" name="$2"
    if [ -f "$pidfile" ]; then
        PID=$(cat "$pidfile")
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID"
            echo "[stop] Stopped $name (PID $PID)"
        else
            echo "[stop] $name already stopped"
        fi
        rm -f "$pidfile"
    else
        echo "[stop] No PID file for $name — not running?"
    fi
}

stop_pid /tmp/stockv2-backend.pid  "backend"
stop_pid /tmp/stockv2-frontend.pid "frontend"
