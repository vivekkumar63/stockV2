from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # External API Keys
    anthropic_api_key: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    angel_one_api_key: str = ""
    angel_one_client_id: str = ""
    angel_one_password: str = ""
    angel_one_totp_secret: str = ""

    # App Security
    api_key: str = "changeme"

    # Trading Config
    trading_mode: str = "paper"
    total_capital: float = 500_000
    paper_capital: float = 500_000
    risk_per_trade_pct: float = 2.0
    max_open_positions: int = 8
    max_single_stock_pct: float = 20.0
    max_sector_pct: float = 35.0
    daily_loss_limit_pct: float = 3.0
    auto_trading_enabled: bool = False

    # Signal Config
    min_confidence_for_alert: float = 0.65
    max_ai_signals_per_day: int = 10

    # App
    host: str = "127.0.0.1"
    port: int = 8000
    db_path: str = "data/stockv2.db"
    data_dir: Path = Path("data")
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost"]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
