import pytest
from datetime import date, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base
import models  # noqa


@pytest.fixture
def db():
    """Function-scoped: each test gets a clean DB."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    Session = sessionmaker(bind=eng)
    session = Session()
    # Active holding
    session.execute(text("""
        INSERT INTO portfolio_holdings
            (symbol, quantity, avg_buy_price, first_buy_date, last_buy_date, is_active)
        VALUES ('TCS', 100, 1000.0, date('now'), date('now'), 1)
    """))
    # Exit rule: sl=930, t1=1150, expire in 10 days
    session.execute(text("""
        INSERT INTO exit_rules
            (order_id, symbol, entry_price, stop_loss_price,
             target_1_price, target_2_price, max_exit_date, partial_exit_at_t1)
        VALUES (1, 'TCS', 1000.0, 930.0, 1150.0, 1200.0, :med, 0)
    """), {"med": str(date.today() + timedelta(days=10))})
    session.commit()
    yield session
    session.close()


def test_stop_loss_triggers_exit(db):
    from domains.portfolio.exit_monitor import ExitMonitor
    exits = ExitMonitor(db).scan_exits({"TCS": 920.0})
    assert len(exits) == 1
    assert exits[0]["reason"] == "stop_loss"
    assert exits[0]["symbol"] == "TCS"


def test_target_hit_triggers_exit(db):
    from domains.portfolio.exit_monitor import ExitMonitor
    exits = ExitMonitor(db).scan_exits({"TCS": 1200.0})
    assert len(exits) == 1
    assert exits[0]["reason"] == "target_hit"


def test_no_exit_between_sl_and_target(db):
    from domains.portfolio.exit_monitor import ExitMonitor
    exits = ExitMonitor(db).scan_exits({"TCS": 1050.0})
    assert exits == []


def test_max_holding_days_triggers_exit(db):
    # Move max_exit_date to yesterday
    past = str(date.today() - timedelta(days=1))
    db.execute(text("UPDATE exit_rules SET max_exit_date=:d WHERE symbol='TCS'"), {"d": past})
    db.commit()
    from domains.portfolio.exit_monitor import ExitMonitor
    exits = ExitMonitor(db).scan_exits({"TCS": 1050.0})
    assert len(exits) == 1
    assert exits[0]["reason"] == "max_holding_days"
