#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# StockV2 — bare-metal installer for Ubuntu 22.04 / 24.04
#
# Usage:
#   chmod +x install.sh
#   sudo ./install.sh
#
# What it does:
#   1. Installs system packages (Python 3.11, Node 20, nginx, etc.)
#   2. Installs Poetry
#   3. Installs Python and Node dependencies
#   4. Builds the frontend
#   5. Configures nginx as a reverse proxy
#   6. Creates a stockv2 system user and systemd service for the backend
#   7. Prompts whether to run the historical data bootstrap
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── Checks ────────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && error "Run as root: sudo ./install.sh"
command -v apt-get &>/dev/null || error "This installer requires apt (Ubuntu/Debian)."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$SCRIPT_DIR"
APP_USER="stockv2"

info "Installing StockV2 from $APP_DIR"

# ── 1. System packages ────────────────────────────────────────────────────────
info "Updating apt and installing system packages..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    software-properties-common curl wget gnupg2 ca-certificates \
    build-essential gcc g++ libffi-dev libssl-dev \
    nginx git unzip lsof

# Python 3.11 (deadsnakes PPA for Ubuntu 22.04; 24.04 ships 3.12 but 3.11 is in main)
if ! python3.11 --version &>/dev/null; then
    info "Installing Python 3.11..."
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -qq
    apt-get install -y python3.11 python3.11-venv python3.11-dev python3-pip
fi
info "Python: $(python3.11 --version)"

# Node.js 20 via NodeSource
if ! node --version 2>/dev/null | grep -q "v20"; then
    info "Installing Node.js 20..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
fi
info "Node: $(node --version) | npm: $(npm --version)"

# ── 2. System user ────────────────────────────────────────────────────────────
if ! id "$APP_USER" &>/dev/null; then
    info "Creating system user '$APP_USER'..."
    useradd --system --shell /bin/bash --home "$APP_DIR" --no-create-home "$APP_USER"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# ── 3. Poetry ─────────────────────────────────────────────────────────────────
POETRY_BIN="/usr/local/bin/poetry"
if ! "$POETRY_BIN" --version &>/dev/null; then
    info "Installing Poetry..."
    curl -sSL https://install.python-poetry.org | POETRY_HOME=/usr/local python3.11 -
fi
info "Poetry: $($POETRY_BIN --version)"

# ── 4. Backend Python dependencies ───────────────────────────────────────────
info "Installing Python dependencies..."
cd "$APP_DIR/backend"
sudo -u "$APP_USER" "$POETRY_BIN" config virtualenvs.in-project true
sudo -u "$APP_USER" "$POETRY_BIN" install --only main --no-interaction

VENV="$APP_DIR/backend/.venv"
info "Virtual env at: $VENV"

# ── 5. Backend .env ───────────────────────────────────────────────────────────
if [ ! -f "$APP_DIR/backend/.env" ]; then
    info "Creating backend/.env from example..."
    cp "$APP_DIR/backend/.env.example" "$APP_DIR/backend/.env"
    chown "$APP_USER:$APP_USER" "$APP_DIR/backend/.env"
    warn "Edit $APP_DIR/backend/.env and fill in your API keys before starting."
fi

# ── 6. Frontend build ─────────────────────────────────────────────────────────
info "Installing frontend Node dependencies..."
cd "$APP_DIR/frontend"
sudo -u "$APP_USER" npm ci

if [ ! -f "$APP_DIR/frontend/.env" ]; then
    info "Creating frontend/.env..."
    # With nginx proxy, frontend calls /api/v1 (relative)
    cat > "$APP_DIR/frontend/.env" <<EOF
VITE_API_BASE=/api/v1
VITE_API_KEY=changeme
EOF
    chown "$APP_USER:$APP_USER" "$APP_DIR/frontend/.env"
    warn "Edit $APP_DIR/frontend/.env — set VITE_API_KEY to match API_KEY in backend/.env"
fi

info "Building frontend..."
sudo -u "$APP_USER" npm run build

# ── 7. Data directory ─────────────────────────────────────────────────────────
mkdir -p "$APP_DIR/data"
chown "$APP_USER:$APP_USER" "$APP_DIR/data"

# ── 8. nginx config ───────────────────────────────────────────────────────────
info "Configuring nginx..."
NGINX_CONF="/etc/nginx/sites-available/stockv2"
cat > "$NGINX_CONF" <<NGINX
server {
    listen 80;
    server_name _;

    gzip on;
    gzip_types text/plain text/css application/javascript application/json;

    # API proxy → FastAPI backend
    location /api/ {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }

    # React SPA
    location / {
        root      $APP_DIR/frontend/dist;
        index     index.html;
        try_files \$uri \$uri/ /index.html;

        location ~* \.(js|css|png|jpg|svg|ico|woff2?)\$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }
}
NGINX

ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/stockv2
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
info "nginx configured and reloaded."

# ── 9. systemd service ────────────────────────────────────────────────────────
info "Creating systemd service..."
cat > /etc/systemd/system/stockv2-backend.service <<SERVICE
[Unit]
Description=StockV2 FastAPI Backend
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR/backend
Environment="PATH=$VENV/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=$APP_DIR/backend/.env
ExecStart=$VENV/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable stockv2-backend
info "systemd service 'stockv2-backend' created and enabled."

# ── 10. Optional: bootstrap historical data ───────────────────────────────────
echo ""
read -rp "Run historical data bootstrap now? This takes 20-60 minutes. (y/N): " RUN_BOOTSTRAP
if [[ "$RUN_BOOTSTRAP" =~ ^[Yy]$ ]]; then
    info "Starting bootstrap... (Ctrl+C to cancel and run manually later)"
    cd "$APP_DIR/backend"
    sudo -u "$APP_USER" "$VENV/bin/python" -m scripts.bootstrap
    info "Bootstrap complete."
else
    info "Skipped. Run manually when ready:"
    info "  cd $APP_DIR/backend && sudo -u $APP_USER .venv/bin/python -m scripts.bootstrap"
fi

# ── 11. Start backend ─────────────────────────────────────────────────────────
info "Starting backend service..."
systemctl start stockv2-backend
sleep 3
if systemctl is-active --quiet stockv2-backend; then
    info "Backend is running."
else
    warn "Backend failed to start. Check logs: journalctl -u stockv2-backend -n 50"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  StockV2 installation complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""
echo "  App URL   : http://$(hostname -I | awk '{print $1}')"
echo "  API health: http://$(hostname -I | awk '{print $1}')/health"
echo ""
echo "  Manage backend:"
echo "    systemctl status  stockv2-backend"
echo "    systemctl restart stockv2-backend"
echo "    journalctl -u stockv2-backend -f"
echo ""
echo "  Config files:"
echo "    $APP_DIR/backend/.env"
echo "    $APP_DIR/frontend/.env"
echo ""
warn "IMPORTANT: Edit backend/.env with real API keys, then restart:"
warn "  systemctl restart stockv2-backend"
