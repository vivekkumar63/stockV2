from unittest.mock import patch, MagicMock
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
import models  # noqa
from domains.data.fundamentals import FundamentalsService


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _mock_ticker(pe=20.0, pb=2.0, eps=50.0, revenue=1e10, net_profit=1e9,
                 de=0.5, roe=0.15, div_yield=0.02):
    mock = MagicMock()
    mock.info = {
        "trailingPE": pe, "priceToBook": pb, "trailingEps": eps,
        "totalRevenue": revenue, "netIncomeToCommon": net_profit,
        "debtToEquity": de, "returnOnEquity": roe, "dividendYield": div_yield,
    }
    return mock


def test_refresh_one_stores_row(db):
    with patch("yfinance.Ticker", return_value=_mock_ticker()):
        result = FundamentalsService(db).refresh_one("RELIANCE")
    assert result is True
    row = db.execute(
        text("SELECT eps, roe, dividend_yield FROM fundamentals WHERE symbol='RELIANCE'")
    ).fetchone()
    assert row is not None
    assert row[0] == pytest.approx(50.0)
    assert row[1] == pytest.approx(0.15)
    assert row[2] == pytest.approx(0.02)


def test_refresh_one_returns_false_on_yfinance_error(db):
    with patch("yfinance.Ticker", side_effect=Exception("network error")):
        result = FundamentalsService(db).refresh_one("BADSTOCK")
    assert result is False


def test_get_latest_returns_populated_dict(db):
    db.execute(text("""
        INSERT INTO fundamentals
            (symbol, pe_ratio, pb_ratio, eps, revenue, net_profit,
             debt_equity, roe, dividend_yield, data_as_of, updated_at)
        VALUES ('TCS', 25.0, 10.0, 120.0, 2e11, 4e10, 0.05, 0.42, 0.012,
                '2026-08-01', datetime('now'))
    """))
    db.commit()
    f = FundamentalsService(db).get_latest("TCS")
    assert f["eps"] == pytest.approx(120.0)
    assert f["roe"] == pytest.approx(0.42)
    assert f["dividend_yield"] == pytest.approx(0.012)
    assert f["data_as_of"] == "2026-08-01"


def test_get_latest_returns_empty_dict_when_no_data(db):
    result = FundamentalsService(db).get_latest("UNKNOWN")
    assert result == {}


def test_refresh_one_overwrites_existing_row(db):
    with patch("yfinance.Ticker", return_value=_mock_ticker(eps=50.0)):
        FundamentalsService(db).refresh_one("INFY")
    with patch("yfinance.Ticker", return_value=_mock_ticker(eps=75.0)):
        FundamentalsService(db).refresh_one("INFY")
    count = db.execute(text("SELECT COUNT(*) FROM fundamentals WHERE symbol='INFY'")).scalar()
    assert count == 1
    row = db.execute(text("SELECT eps FROM fundamentals WHERE symbol='INFY'")).fetchone()
    assert row[0] == pytest.approx(75.0)


def test_refresh_one_normalises_large_de_ratio(db):
    """debtToEquity > 2 from yfinance is a percentage — must divide by 100."""
    with patch("yfinance.Ticker", return_value=_mock_ticker(de=43.5)):
        FundamentalsService(db).refresh_one("WIPRO")
    row = db.execute(
        text("SELECT debt_equity FROM fundamentals WHERE symbol='WIPRO'")
    ).fetchone()
    assert row[0] == pytest.approx(0.435)


def test_refresh_one_keeps_small_de_ratio_as_is(db):
    """debtToEquity <= 2 from yfinance is already a decimal ratio."""
    with patch("yfinance.Ticker", return_value=_mock_ticker(de=0.8)):
        FundamentalsService(db).refresh_one("HCLTECH")
    row = db.execute(
        text("SELECT debt_equity FROM fundamentals WHERE symbol='HCLTECH'")
    ).fetchone()
    assert row[0] == pytest.approx(0.8)
