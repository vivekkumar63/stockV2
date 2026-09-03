"""ZoneAlertScanner — intraday real-time zone price alert engine.

Runs 4× per trading day. For each stock whose live price enters the pre-computed
entry zone (long or short), checks multi-signal confluence and fires a Telegram
photo alert with a dark-theme candlestick chart.
"""
from __future__ import annotations
import html
import io
import json
import logging
import math
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.data.live_price_fetcher import fetch_live_prices

logger = logging.getLogger(__name__)

_BULLISH_CANDLES = {"hammer", "bullish_engulfing", "doji"}
_BEARISH_CANDLES = {"shooting_star", "bearish_engulfing", "doji"}


# ── Chart generation ──────────────────────────────────────────────────────────

def _generate_chart_bytes(
    symbol: str,
    direction: str,
    ohlcv_rows: list,
    result_json: dict,
    live_price: float,
) -> Optional[bytes]:
    """Draw a dark-theme OHLCV candlestick chart with zone bands and setup lines.
    Returns PNG bytes, or None if matplotlib is unavailable."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.debug("[ZoneAlert] matplotlib not available — sending text-only alert")
        return None

    try:
        ohlcv = [
            {
                "date":   str(r[0]),
                "open":   float(r[1]),
                "high":   float(r[2]),
                "low":    float(r[3]),
                "close":  float(r[4]),
                "volume": int(r[5] or 0),
            }
            for r in ohlcv_rows
        ]
        n = len(ohlcv)
        if n < 5:
            return None

        BG       = "#131722"
        PANEL_BG = "#1e2130"
        BULL_CLR = "#26a69a"
        BEAR_CLR = "#ef5350"
        GRID_CLR = "#2a2e3d"
        TEXT_CLR = "#d1d4dc"

        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(14, 8),
            gridspec_kw={"height_ratios": [3, 1]},
            sharex=True,
            facecolor=BG,
        )
        for ax in (ax1, ax2):
            ax.set_facecolor(PANEL_BG)
            ax.tick_params(colors=TEXT_CLR, labelsize=7)
            for spine in ax.spines.values():
                spine.set_edgecolor(GRID_CLR)
            ax.grid(True, alpha=0.25, color=GRID_CLR, linewidth=0.5)

        # Candlesticks
        for i, bar in enumerate(ohlcv):
            clr = BULL_CLR if bar["close"] >= bar["open"] else BEAR_CLR
            ax1.plot([i, i], [bar["low"], bar["high"]], color=clr, linewidth=0.8, zorder=2)
            body = abs(bar["close"] - bar["open"])
            body = max(body, bar["high"] * 0.0005)
            ax1.bar(i, body, bottom=min(bar["open"], bar["close"]),
                    color=clr, width=0.65, zorder=3)

        # Demand zones (green fill)
        for z in result_json.get("demand_zones", []):
            ax1.axhspan(z["low"], z["high"], alpha=0.12, color=BULL_CLR, zorder=1)
            ax1.axhline(y=(z["low"] + z["high"]) / 2, color=BULL_CLR,
                        linewidth=0.4, linestyle=":", alpha=0.4, zorder=1)

        # Supply zones (red fill)
        for z in result_json.get("supply_zones", []):
            ax1.axhspan(z["low"], z["high"], alpha=0.12, color=BEAR_CLR, zorder=1)
            ax1.axhline(y=(z["low"] + z["high"]) / 2, color=BEAR_CLR,
                        linewidth=0.4, linestyle=":", alpha=0.4, zorder=1)

        # Setup lines (entry / SL / T1 / T2)
        setup_key = "long_setup" if direction == "LONG" else "short_setup"
        setup = result_json.get(setup_key) or {}
        if setup:
            ax1.axhline(y=setup["ideal_entry"], color="#29b6f6", linestyle="--",
                        linewidth=2.0, label=f"Entry ₹{setup['ideal_entry']:,.0f}", zorder=5)
            ax1.axhline(y=setup["stop_loss"], color=BEAR_CLR, linestyle="--",
                        linewidth=1.5, label=f"SL ₹{setup['stop_loss']:,.0f}", zorder=5)
            ax1.axhline(y=setup["t1"], color="#66bb6a", linestyle="--",
                        linewidth=1.2, label=f"T1 ₹{setup['t1']:,.0f} (1:{setup['t1_rr']})", zorder=5)
            ax1.axhline(y=setup["t2"], color="#a5d6a7", linestyle="--",
                        linewidth=1.0, label=f"T2 ₹{setup['t2']:,.0f}", zorder=5)

        # Live price dotted horizontal line
        ax1.axhline(y=live_price, color="#ffd54f", linestyle="-",
                    linewidth=1.5, label=f"Live ₹{live_price:,.0f}", zorder=5, alpha=0.9)

        # Volume bars
        for i, bar in enumerate(ohlcv):
            clr = BULL_CLR if bar["close"] >= bar["open"] else BEAR_CLR
            ax2.bar(i, bar["volume"], color=clr, alpha=0.6, width=0.65)
        ax2.yaxis.set_visible(False)

        # X-axis ticks (dates)
        step = max(1, n // 8)
        ticks = list(range(0, n, step))
        ax2.set_xticks(ticks)
        ax2.set_xticklabels([ohlcv[i]["date"] for i in ticks],
                            rotation=40, fontsize=6, color=TEXT_CLR)

        ax1.legend(fontsize=8, loc="upper left", facecolor=PANEL_BG,
                   labelcolor=TEXT_CLR, edgecolor=GRID_CLR)

        title_clr = BULL_CLR if direction == "LONG" else BEAR_CLR
        ax1.set_title(f"{symbol} — {direction} ZONE ALERT",
                      fontsize=13, fontweight="bold", color=title_clr, pad=10)
        fig.patch.set_facecolor(BG)

        plt.tight_layout(pad=0.8)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor=BG)
        buf.seek(0)
        plt.close(fig)
        return buf.getvalue()

    except Exception as e:
        logger.warning("[ZoneAlert] chart generation failed: %s", e)
        try:
            import matplotlib.pyplot as _plt
            _plt.close("all")
        except Exception:
            pass
        return None


# ── Confluence check ──────────────────────────────────────────────────────────

def _confluence(
    direction: str,
    *,
    market_structure: str,
    candle_signal: str,
    position_tag: str,
    setup_score: Optional[float],
    zone_score: Optional[float],
    best_rr: Optional[float],
    rvol: Optional[float],
) -> tuple[int, list[str], list[str]]:
    """Return (score, conditions_met, conditions_failed) for a potential entry."""
    met: list[str] = []
    failed: list[str] = []

    def _chk(label: str, cond: bool) -> None:
        (met if cond else failed).append(label)

    if direction == "LONG":
        _chk("Market not bearish",           market_structure in ("bullish", "sideways"))
        _chk("Market bullish (trend assist)", market_structure == "bullish")
        _chk("Bullish candle pattern",        candle_signal in _BULLISH_CANDLES)
        _chk("Price at/in demand zone",       position_tag in ("in_demand", "near_demand"))
        _chk("Long setup score ≥ 60",         (setup_score or 0) >= 60)
        _chk("Demand zone score ≥ 60",        (zone_score or 0) >= 60)
        _chk("R:R ≥ 1.5",                    (best_rr or 0) >= 1.5)
        _chk("Volume elevated (RVol ≥ 1.2)", (rvol or 0) >= 1.2)
    else:
        _chk("Market not bullish",            market_structure in ("bearish", "sideways"))
        _chk("Market bearish (trend assist)", market_structure == "bearish")
        _chk("Bearish candle pattern",        candle_signal in _BEARISH_CANDLES)
        _chk("Price at/in supply zone",       position_tag in ("in_supply", "near_supply"))
        _chk("Short setup score ≥ 60",        (setup_score or 0) >= 60)
        _chk("Supply zone score ≥ 60",        (zone_score or 0) >= 60)
        _chk("R:R ≥ 1.5",                    (best_rr or 0) >= 1.5)
        _chk("Volume elevated (RVol ≥ 1.2)", (rvol or 0) >= 1.2)

    return len(met), met, failed


# ── Scanner ───────────────────────────────────────────────────────────────────

class ZoneAlertScanner:
    """Check live prices against pre-computed zone entry levels and fire Telegram alerts."""

    MIN_CONFLUENCE   = 5    # out of 8 signals required
    ENTRY_TOLERANCE  = 0.012  # ±1.2% of entry price

    # ── public API ────────────────────────────────────────────────────────────

    def scan_and_alert(self, db: Session) -> int:
        """Run full intraday scan. Returns number of alerts sent."""
        today = date.today()
        rows = db.execute(
            text("""
                SELECT symbol,
                       long_entry_price, short_entry_price,
                       long_setup_score,  short_setup_score,
                       best_demand_score, best_supply_score,
                       best_long_rr,      best_short_rr,
                       position_tag,      rvol_at_compute,
                       result_json
                FROM zone_analysis_results
                WHERE computed_date = :dt
                  AND (long_entry_price IS NOT NULL OR short_entry_price IS NOT NULL)
            """),
            {"dt": str(today)},
        ).fetchall()

        if not rows:
            logger.info("[ZoneAlert] no zone data for %s", today)
            return 0

        symbols    = [r[0] for r in rows]
        live_prices = fetch_live_prices(symbols)
        if not live_prices:
            logger.warning("[ZoneAlert] live price fetch returned empty — skipping scan")
            return 0

        alerts_sent = 0
        for row in rows:
            (sym, long_ep, short_ep,
             long_sc, short_sc, dem_sc, sup_sc,
             long_rr, short_rr,
             pos_tag, rvol, rj_raw) = row

            price = live_prices.get(sym)
            if not price or not math.isfinite(price) or price <= 0:
                continue

            rj = rj_raw if isinstance(rj_raw, dict) else json.loads(rj_raw or "{}")
            mkt    = rj.get("market_structure", "sideways")
            candle = rj.get("candle_signal", "NONE")

            for direction, ep, sc, zsc, rr in [
                ("LONG",  long_ep,  long_sc,  dem_sc, long_rr),
                ("SHORT", short_ep, short_sc, sup_sc, short_rr),
            ]:
                if not ep:
                    continue
                if not self._near_entry(price, float(ep)):
                    continue
                if self._already_alerted(db, sym, direction, today):
                    continue

                score, met, failed = _confluence(
                    direction,
                    market_structure=mkt,
                    candle_signal=candle,
                    position_tag=pos_tag or "",
                    setup_score=sc,
                    zone_score=zsc,
                    best_rr=rr,
                    rvol=rvol,
                )
                if score < self.MIN_CONFLUENCE:
                    logger.debug("[ZoneAlert] %s %s confluence %d/%d — skipped",
                                 sym, direction, score, self.MIN_CONFLUENCE)
                    continue

                if self._send_alert(db, sym, direction, price, float(ep),
                                    rj, score, met, failed, today):
                    alerts_sent += 1

        logger.info("[ZoneAlert] scan complete — %d alert(s) sent", alerts_sent)
        return alerts_sent

    # ── helpers ───────────────────────────────────────────────────────────────

    def _near_entry(self, price: float, entry: float) -> bool:
        return abs(price - entry) / entry <= self.ENTRY_TOLERANCE

    def _already_alerted(self, db: Session, symbol: str, direction: str, today: date) -> bool:
        row = db.execute(
            text("""
                SELECT 1 FROM zone_price_alerts_sent
                WHERE symbol = :s AND direction = :d AND alert_date = :dt LIMIT 1
            """),
            {"s": symbol, "d": direction, "dt": str(today)},
        ).fetchone()
        return row is not None

    def _send_alert(
        self,
        db: Session,
        symbol: str,
        direction: str,
        price: float,
        entry: float,
        result_json: dict,
        confluence_score: int,
        met: list[str],
        failed: list[str],
        today: date,
    ) -> bool:
        from domains.alerts.telegram import AlertService

        # Fetch last 60 OHLCV bars for chart
        ohlcv_rows = db.execute(
            text("""
                SELECT date, open, high, low, close, volume FROM (
                    SELECT date, open, high, low, close, volume
                    FROM stock_prices_daily WHERE symbol = :s
                    ORDER BY date DESC LIMIT 60
                ) sub ORDER BY date ASC
            """),
            {"s": symbol},
        ).fetchall()

        chart_bytes = _generate_chart_bytes(symbol, direction, ohlcv_rows, result_json, price)

        setup_key = "long_setup" if direction == "LONG" else "short_setup"
        setup     = result_json.get(setup_key) or {}
        mkt       = result_json.get("market_structure", "sideways")
        candle    = result_json.get("candle_signal", "NONE")
        icon      = "🟢" if direction == "LONG" else "🔴"

        # Build message
        lines = [
            f"{icon} <b>{html.escape(symbol)} — {direction} ZONE ALERT</b>",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            f"\n💰 <b>Live Price:</b> ₹{price:,.2f}   <b>Entry Zone:</b> ₹{entry:,.0f}",
            f"📊 <b>Market:</b> {mkt.upper()}   "
            f"🕯 <b>Candle:</b> {candle.replace('_', ' ').title() if candle != 'NONE' else '—'}",
        ]

        if setup:
            pct_to_sl = abs(setup["stop_loss"] - entry) / entry * 100
            lines += [
                f"",
                f"<b>Setup ({direction}):</b>",
                f"  Entry:    ₹{setup['ideal_entry']:,.0f}",
                f"  Stop Loss:₹{setup['stop_loss']:,.0f}  ({pct_to_sl:.1f}% risk)",
                f"  Target 1: ₹{setup['t1']:,.0f}  (R:R 1:{setup['t1_rr']})",
                f"  Target 2: ₹{setup['t2']:,.0f}  (R:R 1:{setup['t2_rr']})",
            ]
            if setup.get("explanation"):
                lines.append(f"\n<i>{html.escape(setup['explanation'][:200])}</i>")

        lines += [
            f"",
            f"<b>✅ Signals aligned ({confluence_score}/8):</b>",
        ]
        lines += [f"  ✅ {html.escape(c)}" for c in met]
        if failed:
            lines.append(f"<b>❌ Not met:</b>")
            lines += [f"  ❌ {html.escape(c)}" for c in failed[:3]]

        if direction == "LONG":
            lines.append("\n⚡ <b>Action:</b> Watch for entry at demand zone. Confirm with 15-min chart.")
        else:
            lines.append("\n⚡ <b>Action:</b> Watch for entry at supply zone. Confirm with 15-min chart.")

        caption = "\n".join(lines)

        ok = AlertService().send_zone_photo_alert(caption, chart_bytes)
        if not ok:
            return False

        try:
            db.execute(
                text("""
                    INSERT INTO zone_price_alerts_sent (symbol, direction, alert_date, price_at_alert)
                    VALUES (:s, :d, :dt, :p)
                    ON CONFLICT (symbol, direction, alert_date) DO NOTHING
                """),
                {"s": symbol, "d": direction, "dt": str(today), "p": round(price, 2)},
            )
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning("[ZoneAlert] failed to record sent alert for %s/%s: %s", symbol, direction, e)

        logger.info("[ZoneAlert] ✅ %s %s alert sent (confluence %d/8)", symbol, direction, confluence_score)
        return True
