import logging
from datetime import datetime, time as dtime
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)


class AngelOneFeed:
    """Live market data via Angel One SmartAPI.

    Connection is lazy — call connect() explicitly before get_quote().
    When credentials are empty (e.g. in tests), connect() is a no-op.
    """

    def __init__(self, api_key: str, client_id: str, password: str, totp_secret: str):
        self._api_key = api_key
        self._client_id = client_id
        self._password = password
        self._totp_secret = totp_secret
        self._api = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        """Attempt to authenticate with Angel One. Returns True on success."""
        if not self._api_key or not self._client_id:
            logger.warning("Angel One credentials not configured — live feed disabled")
            return False
        try:
            import pyotp
            from SmartApi import SmartConnect

            obj = SmartConnect(api_key=self._api_key)
            totp = pyotp.TOTP(self._totp_secret).now()
            data = obj.generateSession(self._client_id, self._password, totp)
            if data.get("status"):
                self._api = obj
                self._connected = True
                logger.info("Angel One connected successfully")
                return True
            logger.error("Angel One session failed: %s", data.get("message"))
            return False
        except Exception as e:
            logger.error("Angel One connection error: %s", e)
            return False

    def get_quote(self, symbol: str) -> Optional[dict]:
        """Fetch latest trade price for a single symbol.

        Returns dict with keys: symbol, ltp, open, high, low, close, volume.
        Returns None on any error or if not connected.
        """
        if not self._connected or self._api is None:
            return None
        try:
            token = self._get_token(symbol)
            if not token:
                return None
            response = self._api.getMarketData(
                mode="LTP",
                exchangeTokens={"NSE": [token]},
            )
            if not response.get("status"):
                return None
            fetched = response.get("data", {}).get("fetched", [])
            if not fetched:
                return None
            row = fetched[0]
            return {
                "symbol": symbol,
                "ltp": row.get("ltp"),
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "close": row.get("close"),
                "volume": row.get("tradeVolume"),
                "timestamp": datetime.now(IST).isoformat(),
            }
        except Exception as e:
            logger.warning("get_quote failed for %s: %s", symbol, e)
            return None

    def get_quotes_bulk(self, symbols: list[str]) -> dict[str, Optional[dict]]:
        """Fetch quotes for multiple symbols. Returns {symbol: quote_dict_or_None}."""
        return {sym: self.get_quote(sym) for sym in symbols}

    def is_market_hours(self) -> bool:
        """Return True if current IST time is within NSE trading hours."""
        now_ist = datetime.now(IST)
        if now_ist.weekday() >= 5:
            return False
        return MARKET_OPEN <= now_ist.time() <= MARKET_CLOSE

    def _get_token(self, symbol: str) -> Optional[str]:
        """Map NSE symbol to Angel One exchange token.

        Stub — full token map loaded in Plan 2.
        """
        return None
