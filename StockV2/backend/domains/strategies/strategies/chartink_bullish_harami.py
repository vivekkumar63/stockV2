import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkBullishHarami(BaseStrategy):
    """Chartink: Bullish Harami — small green candle inside a large red candle, bottom reversal."""
    name = "Chartink Bullish Harami Pattern"
    description = "Small green candle body inside prev large red candle + RSI oversold + volume"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 1
    max_holding_days = 5

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 22:
            return Signal("NONE")

        r = df.iloc[-1]
        r_prev = df.iloc[-2]

        o0 = float(r["open"])
        c0 = float(r["close"])
        o1 = float(r_prev["open"])
        c1 = float(r_prev["close"])
        h1 = float(r_prev["high"])
        lo1 = float(r_prev["low"])
        rsi = r["rsi_14"]
        vol_ratio = r["volume_ratio"]

        if any(pd.isna(x) for x in [rsi, vol_ratio]):
            return Signal("NONE")

        met, failed = [], []

        if c1 < o1:
            prev_body = o1 - c1
            met.append(f"Prev red candle body {prev_body:.2f} ({o1:.1f}→{c1:.1f})")
        else:
            failed.append(f"Prev candle was green (no Harami setup)")

        if c0 > o0:
            met.append(f"Today green candle ({o0:.1f}→{c0:.1f})")
        else:
            failed.append(f"Today red candle (not a Harami)")

        today_body_hi = max(o0, c0)
        today_body_lo = min(o0, c0)
        prev_body_hi = max(o1, c1)
        prev_body_lo = min(o1, c1)

        if today_body_hi <= prev_body_hi and today_body_lo >= prev_body_lo:
            containment_pct = (today_body_hi - today_body_lo) / (prev_body_hi - prev_body_lo) * 100 if prev_body_hi > prev_body_lo else 0
            met.append(f"Body contained within prev red body ({containment_pct:.0f}% size)")
        else:
            failed.append(f"Body not inside prev candle body")

        if rsi < 50:
            met.append(f"RSI {rsi:.1f} < 50 (bearish zone, potential reversal)")
        else:
            failed.append(f"RSI {rsi:.1f} ≥ 50 (not oversold)")

        if vol_ratio < 1.0:
            met.append(f"Lower volume {vol_ratio:.2f}x (harami expected to have lower vol)")
        else:
            failed.append(f"Higher volume on harami {vol_ratio:.2f}x (unusual)")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        body_ratio = (today_body_hi - today_body_lo) / (o1 - c1) if (o1 - c1) > 0 else 1
        confidence = min(0.72, 0.50 + (1 - body_ratio) * 0.15 + (len(met) - 3) * 0.04)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.55,
            expected_upside_pct=4.0,
            stop_loss_pct=3.0,
            target_pct=5.0,
            holding_days=3,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14", "volume_ratio"]
