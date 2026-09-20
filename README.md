# StockV2 — Setup Guide

Single-user NSE stock trading platform: live data, 55 strategies, backtesting, paper trading, React frontend.

---

## Choose your deployment method

| Method | Best for | Time |
|---|---|---|
| **A. Docker** (recommended) | VM / server, clean install | ~15 min |
| **B. Bare-metal script** | Ubuntu 22.04/24.04, full control | ~20 min |
| **C. Local dev** | Development on your machine | ~10 min |

---

## Method A — Docker (recommended for VM)

### Prerequisites
- Docker 24+ and Docker Compose v2
- VM with 2 GB RAM, 4 GB disk

### Steps

```bash
# 1. Clone
git clone <repo-url>
cd StockV2

# 2. Create .env from template
cp .env.example .env
nano .env          # fill in API_KEY and any other keys you have

# 3. Create data directory (holds the SQLite database)
mkdir -p data

# 4. Build and start
docker compose up -d --build

# 5. Run historical data bootstrap (first time only, 20-60 min)
docker compose exec backend python -m scripts.bootstrap
```

App runs at **http://your-vm-ip** (port 80 via nginx).
API docs at **http://your-vm-ip/docs** (proxied from backend).

### Useful Docker commands

```bash
docker compose ps                          # check status
docker compose logs -f backend             # backend logs
docker compose restart backend             # restart after config change
docker compose down && docker compose up -d --build   # full rebuild
```

---

## Method B — Bare-metal (Ubuntu 22.04 / 24.04)

```bash
git clone <repo-url>
cd StockV2
chmod +x install.sh scripts/*.sh
sudo ./install.sh
```

The installer:
1. Installs Python 3.11, Node 20, nginx
2. Installs all dependencies
3. Builds the frontend
4. Configures nginx (port 80 → React + /api → FastAPI)
5. Creates a `stockv2-backend` systemd service (auto-start on boot)
6. Optionally runs the data bootstrap

After install, edit config and restart:
```bash
sudo nano /path/to/StockV2/backend/.env
sudo systemctl restart stockv2-backend
```

### Bare-metal management

```bash
sudo systemctl status  stockv2-backend     # status
sudo systemctl restart stockv2-backend     # restart
sudo ./scripts/logs.sh                     # tail logs
sudo ./scripts/update.sh                   # pull + rebuild + restart
```

---

## Method C — Local development

### Prerequisites

| Tool | Version |
|---|---|
| Python | 3.11+ |
| Poetry | 1.7+ |
| Node.js | 20+ |

### Steps

```bash
# Backend
cd backend
poetry install
cp .env.example .env    # fill in API_KEY at minimum
poetry run uvicorn main:app --reload
# → http://localhost:8000

# Frontend (new terminal)
cd frontend
npm install
cp .env.example .env    # VITE_API_BASE=http://localhost:8000/api/v1
npm run dev
# → http://localhost:3000
```

### First run: load historical data (once only)

```bash
cd backend
poetry run python -m scripts.bootstrap
```
Downloads 15 years of OHLCV data for all NSE stocks. Takes 20–60 min. Resumable.

---

## Configuration reference

### Backend — `backend/.env`

| Variable | Required | Description |
|---|---|---|
| `API_KEY` | Yes | Shared secret for frontend ↔ backend auth |
| `ANTHROPIC_API_KEY` | For AI features | Claude signal explanations |
| `ANGEL_ONE_API_KEY` | For live data | Live price feed during market hours |
| `ANGEL_ONE_CLIENT_ID` | For live data | |
| `ANGEL_ONE_PASSWORD` | For live data | |
| `ANGEL_ONE_TOTP_SECRET` | For live data | Base32 2FA secret from AngelOne |
| `TELEGRAM_BOT_TOKEN` | Optional | Daily digest alerts |
| `TELEGRAM_CHAT_ID` | Optional | Your Telegram chat/channel ID |
| `TRADING_MODE` | No | `paper` (default) or `live` |
| `TOTAL_CAPITAL` | No | Total capital for position sizing (default: 500000) |
| `CORS_ORIGINS` | No | JSON list of allowed origins (default: localhost) |

### Frontend — `frontend/.env`

| Variable | Description |
|---|---|
| `VITE_API_BASE` | API base URL. Use `/api/v1` with nginx proxy, or `http://host:8000/api/v1` for direct |
| `VITE_API_KEY` | Must match `API_KEY` in backend `.env` |

---

## Adding a new strategy

Drop a `.py` file in `backend/domains/strategies/strategies/`. Copy `_template.py` as a starting point. On next restart, it is auto-discovered, seeded to the DB, and appears in the UI.

```bash
cp backend/domains/strategies/strategies/_template.py \
   backend/domains/strategies/strategies/my_strategy.py
# edit my_strategy.py
systemctl restart stockv2-backend   # bare-metal
# or: docker compose restart backend
```

---

## Scheduled jobs (automatic)

The backend scheduler starts with the app. All times in IST:

| Job | Schedule | What it does |
|---|---|---|
| Intraday scan | Every 15 min, 9am–3pm Mon–Fri | Runs all strategies, monitors exits |
| Daily EOD update | 4:00pm Mon–Fri | Generates end-of-day signals |
| Daily digest | 5:15pm Mon–Fri | Sends top signals to Telegram |

---

## Tests

```bash
# Backend (18 tests)
cd backend && poetry run pytest tests/ -v

# Frontend (22 tests)
cd frontend && npm run test:run
```

---

## Key API endpoints

All endpoints require header `X-API-Key: <your API_KEY>`.

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/signals/today` | Today's BUY/SELL signals |
| GET | `/api/v1/strategies` | All 55 strategies |
| GET | `/api/v1/portfolio/summary` | Capital and position summary |
| POST | `/api/v1/backtest/run` | Run a backtest |
| POST | `/api/v1/backtest/scan` | Scan all stocks with all strategies |
| GET | `/health` | Health check (no auth) |

Full docs at `http://localhost:8000/docs`.

---

## Project structure

```
StockV2/
├── Dockerfile.backend
├── Dockerfile.frontend
├── docker-compose.yml
├── nginx/nginx.conf
├── install.sh              ← bare-metal Ubuntu installer
├── scripts/
│   ├── start.sh / stop.sh  ← manual start/stop
│   ├── update.sh           ← git pull + rebuild + restart
│   ├── logs.sh             ← tail backend logs
│   └── docker-rebuild.sh   ← full Docker rebuild
├── backend/
│   ├── domains/
│   │   ├── strategies/strategies/   ← drop new .py files here
│   │   ├── backtest/
│   │   ├── data/
│   │   ├── portfolio/
│   │   └── ai/
│   ├── main.py
│   ├── settings.py
│   └── stockv2.db          ← auto-created, git-ignored
└── frontend/src/
    ├── pages/
    └── api/
```
