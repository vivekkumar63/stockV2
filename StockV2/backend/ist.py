from datetime import date, datetime
from zoneinfo import ZoneInfo

_IST = ZoneInfo("Asia/Kolkata")


def ist_now() -> datetime:
    """Current datetime in IST."""
    return datetime.now(_IST)


def ist_today() -> date:
    """Current date in IST (safe across UTC midnight)."""
    return ist_now().date()
