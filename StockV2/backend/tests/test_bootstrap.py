import pytest
from unittest.mock import patch
import pandas as pd
from scripts.bootstrap import BootstrapRunner


@pytest.fixture
def mock_db():
    """In-memory test database."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from database import Base
    import models  # noqa

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def test_bootstrap_skips_already_downloaded_symbols(mock_db):
    """If a symbol already has data, it should be skipped."""
    from sqlalchemy import text
    mock_db.execute(text(
        "INSERT INTO stock_prices_daily (symbol, date, open, high, low, close, volume, data_source)"
        " VALUES ('RELIANCE', '2024-01-01', 100, 101, 99, 100, 1000000, 'yfinance')"
    ))
    mock_db.commit()

    runner = BootstrapRunner(db=mock_db, symbols=["RELIANCE"])
    with patch.object(runner.feed, "download") as mock_download:
        mock_download.return_value = pd.DataFrame()
        runner.run(years=1)
        mock_download.assert_not_called()


def test_bootstrap_downloads_and_saves_new_symbol(mock_db):
    """A symbol with no data should be downloaded and saved."""
    dates = pd.date_range("2024-01-01", periods=3, freq="B")
    mock_df = pd.DataFrame({
        "open": [100.0, 101.0, 102.0],
        "high": [101.0, 102.0, 103.0],
        "low": [99.0, 100.0, 101.0],
        "close": [100.5, 101.5, 102.5],
        "volume": [1_000_000, 1_200_000, 900_000],
    }, index=dates)

    runner = BootstrapRunner(db=mock_db, symbols=["TCS"])
    with patch.object(runner.feed, "download", return_value=mock_df):
        stats = runner.run(years=1)

    assert stats["downloaded"] >= 1


def test_bootstrap_inserts_symbol_into_stocks_table(mock_db):
    dates = pd.date_range("2024-01-01", periods=2, freq="B")
    mock_df = pd.DataFrame({
        "open": [500.0, 501.0], "high": [502.0, 503.0],
        "low": [499.0, 500.0], "close": [501.0, 502.0],
        "volume": [500_000, 600_000],
    }, index=dates)

    runner = BootstrapRunner(db=mock_db, symbols=["INFY"])
    with patch.object(runner.feed, "download", return_value=mock_df):
        runner.run(years=1)

    from sqlalchemy import text
    result = mock_db.execute(text("SELECT symbol FROM stocks WHERE symbol='INFY'")).fetchone()
    assert result is not None
