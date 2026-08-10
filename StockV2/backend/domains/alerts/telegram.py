import logging
from datetime import date
from typing import Optional

import httpx

from settings import settings

logger = logging.getLogger(__name__)


class AlertService:
    def __init__(self):
        self._token = settings.telegram_bot_token
        self._chat_id = settings.telegram_chat_id

    def _enabled(self) -> bool:
        return bool(self._token and self._chat_id)

    def send(self, text: str) -> bool:
        if not self._enabled():
            logger.debug("[AlertService] Telegram not configured, skipping send")
            return False
        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        try:
            r = httpx.post(
                url,
                json={"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"},
                timeout=10.0,
            )
            if r.status_code != 200:
                logger.error("[AlertService] Telegram API error %d: %s", r.status_code, r.text)
                return False
            return True
        except Exception as e:
            logger.error("[AlertService] Send failed: %s", e)
            return False

    def send_daily_digest(self, top_signals: list[dict], scan_date: Optional[date] = None) -> bool:
        today = scan_date or date.today()
        lines = [
            f"<b>📊 StockV2 Daily Digest — {today.strftime('%d %b %Y')}</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]
        if top_signals:
            lines.append(f"\n<b>TOP BUY SIGNALS TODAY ({len(top_signals)}):</b>")
            for sig in top_signals[:10]:
                pct = int((sig.get("confidence_score") or 0) * 100)
                strategy = sig.get("strategy_name", "")
                lines.append(f"  🟢 <b>{sig['symbol']}</b> — {pct}% confidence ({strategy})")
        else:
            lines.append("\nNo high-confidence signals today.")
        return self.send("\n".join(lines))
