import json
import logging
from datetime import date
from typing import Optional

import httpx

from settings import settings
from ist import ist_today

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
        today = scan_date or ist_today()
        lines = [
            f"<b>📊 StockV2 Daily Digest — {today.strftime('%d %b %Y')}</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]
        if not top_signals:
            lines.append("\nNo high-confidence BUY signals today.")
            return self.send("\n".join(lines))

        lines.append(f"\n<b>TOP BUY SIGNALS ({len(top_signals)}):</b>")
        for sig in top_signals[:10]:
            conf = int((sig.get("confidence_score") or 0) * 100)
            price = sig.get("price_at_signal")
            sl = sig.get("suggested_stop_loss")
            tgt = sig.get("suggested_target")
            upside = sig.get("expected_upside_pct")
            hold = sig.get("holding_period_days")
            strategy = sig.get("strategy_name", "")
            win_rate = sig.get("historical_win_rate")

            # Format prices
            price_str = f"₹{price:,.0f}" if price else "—"
            sl_str = f"₹{sl:,.0f}" if sl else "—"
            tgt_str = f"₹{tgt:,.0f}" if tgt else "—"
            win_str = f"{int(win_rate * 100)}% hist. win rate" if win_rate is not None else "no history yet"

            # Parse reasoning
            conditions: list[str] = []
            try:
                reasoning = json.loads(sig.get("reasoning_json") or "{}")
                conditions = reasoning.get("conditions_met", [])
            except Exception:
                pass
            why = " | ".join(conditions[:3]) if conditions else strategy

            lines.append(
                f"\n🟢 <b>{sig['symbol']}</b> — {conf}% confidence\n"
                f"   📌 {strategy}\n"
                f"   💰 Price: {price_str}  |  SL: {sl_str}  |  Target: {tgt_str}\n"
                + (f"   📈 Upside: {upside:.1f}%  |  Hold: {hold}d\n" if upside and hold else "")
                + f"   📊 {win_str}\n"
                + f"   💡 <i>{why}</i>"
            )

        return self.send("\n".join(lines))

    def send_sell_alerts(self, alerts: list[dict]) -> bool:
        if not alerts:
            return True
        lines = [
            f"<b>🚨 SELL ALERT — {len(alerts)} held stock{'s' if len(alerts) > 1 else ''} flagged</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        ]
        for a in alerts:
            conf = int((a.get("confidence_score") or 0) * 100)
            price = a.get("price_at_signal")
            avg = a.get("avg_buy_price")
            strategy = a.get("strategy_name", "")
            signal_date = a.get("signal_date", "")

            pnl_str = ""
            if price and avg:
                pnl_pct = (price - avg) / avg * 100
                pnl_str = f"  |  P&L est: {pnl_pct:+.1f}%"

            conditions: list[str] = []
            try:
                reasoning = json.loads(a.get("reasoning_json") or "{}")
                conditions = reasoning.get("conditions_met", [])
            except Exception:
                pass
            why = " | ".join(conditions[:2]) if conditions else strategy

            lines.append(
                f"\n🔴 <b>{a['symbol']}</b> — {conf}% confidence{pnl_str}\n"
                f"   📌 {strategy}\n"
                f"   💰 Signal price: ₹{price:,.0f}  (date: {signal_date})\n"
                f"   💡 <i>{why}</i>"
            )
        return self.send("\n".join(lines))

    def send_entry_alert(
        self,
        signal: dict,
        current_price: float,
        fii_dii_row: Optional[dict] = None,
    ) -> bool:
        """Send an individual entry-window alert for a BUY signal."""
        sym = signal.get("symbol", "")
        strategy = signal.get("strategy_name", "")
        entry_price = float(signal.get("price_at_signal") or current_price)
        pct = (current_price - entry_price) / entry_price * 100

        win_rate = signal.get("historical_win_rate")
        win_str = f"{int(win_rate * 100)}%" if win_rate is not None else "N/A"

        score = signal.get("opportunity_score")
        grade = signal.get("opportunity_grade") or ""
        score_str = f"{score}/100 [{grade}]" if score is not None else "—"

        stop_loss = signal.get("suggested_stop_loss")
        target = signal.get("suggested_target")
        sl_str = f"₹{stop_loss:,.1f} ({(stop_loss - current_price)/current_price*100:.1f}%)" if stop_loss else "—"
        tgt_str = f"₹{target:,.1f} ({(target - current_price)/current_price*100:+.1f}%)" if target else "—"

        fii_dii_line = ""
        if fii_dii_row:
            fii_net = fii_dii_row.get("fii_net_equity") or 0
            dii_net = fii_dii_row.get("dii_net_equity") or 0
            flow_emoji = "🟢" if fii_net > 0 else "🔴"
            fii_dii_line = (
                f"\n<b>FII/DII:</b>   FII {fii_net:+,.0f} Cr | DII {dii_net:+,.0f} Cr {flow_emoji}"
            )

        text = (
            f"🚨 <b>Entry Window — {sym}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"\n<b>Signal:</b>     {strategy} ({win_str} win rate)"
            f"\n<b>Entry:</b>      ₹{current_price:,.1f}  (signal ₹{entry_price:,.1f}, {pct:+.1f}%)"
            f"\n<b>Target:</b>     {tgt_str}"
            f"\n<b>Stop Loss:</b>  {sl_str}"
            f"\n<b>Score:</b>      {score_str}"
            f"{fii_dii_line}"
        )
        return self.send(text)

    def send_special_scan_alerts(self, signals: list[dict], scan_date: Optional[date] = None) -> bool:
        """Send BUY signals from Special Strategies scan."""
        if not signals:
            return True
        today = scan_date or ist_today()
        lines = [
            f"<b>⭐ Special Strategies — {today.strftime('%d %b %Y')}</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"\n<b>BUY SIGNALS ({len(signals)}):</b>",
        ]
        for sig in signals[:10]:
            conf = int((sig.get("confidence") or 0) * 100)
            price = sig.get("price")
            strategy = sig.get("strategy_name", "")
            conditions = sig.get("conditions_met") or []
            why = " | ".join(conditions[:2]) if conditions else strategy
            price_str = f"₹{price:,.2f}" if price else "—"
            lines.append(
                f"\n🟢 <b>{sig['symbol']}</b> — {conf}% confidence\n"
                f"   📌 {strategy}\n"
                f"   💰 Price: {price_str}\n"
                f"   💡 <i>{why}</i>"
            )
        return self.send("\n".join(lines))
