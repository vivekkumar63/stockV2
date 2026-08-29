import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkBearishEngulfing(BaseStrategy):
    """Chartink: Bearish Engulfing — today's red candle body fully engulfs previous green candle."""
    name = "Chartink Bearish Engulfing Reversal"
    description = "Today red candle engulfs prev green + RSI > 60 + volume expanding = distribution top"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 1
    max_holding_days = 7

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 22:
            return Signal("NONE")

        r = df.iloc[-1]
        r_prev = df.iloc[-2]

        o0 = float(r["open"])
        c0 = float(r["close"])
        o1 = float(r_prev["open"])
        c1 = float(r_prev["close"])
        v0 = float(r["volume"])
        v1 = float(r_prev["volume"])
        rsi = r["rsi_14"]
        sma20 = r["sma_20"]

        if any(pd.isna(x) for x in [rsi, sma20]):
            return Signal("NONE")

        met, failed = [], []

        if c1 > o1:
            met.append(f"Prev candle green ({o1:.1f}→{c1:.1f})")
        else:
            failed.append(f"Prev candle was red (no engulfing pattern)")

        if c0 < o0:
            met.append(f"Today red candle ({o0:.1f}→{c0:.1f})")
        else:
            failed.append(f"Today green (no bearish reversal)")

        if o0 >= c1 and c0 <= o1:
            prev_body = c1 - o1
            engulf_pct = (o0 - c0) / prev_body * 100 if prev_body > 0 else 100.0
            met.append(f"Full engulfment: today body covers prev body ({engulf_pct:.0f}%)")
        elif o0 >= c1:
            met.append(f"Partial engulf: opened above prev close {c1:.1f}")
        else:
            failed.append(f"No engulfment (today body {min(o0,c0):.1f}-{max(o0,c0):.1f} vs prev {o1:.1f}-{c1:.1f})")

        if rsi > 60:
            met.append(f"RSI {rsi:.1f} > 60 (reversing from overbought zone)")
        else:
            failed.append(f"RSI {rsi:.1f} not in overbought zone")

        if v1 > 0 and v0 > v1:
            met.append(f"Volume expanding ({v0:,.0f} > prev {v1:,.0f})")
        else:
            failed.append(f"Volume not expanding")

        if c0 > sma20:
            met.append(f"Still above SMA20 {sma20:.1f} (distribution zone)")
        else:
            failed.append(f"Already below SMA20 (already broken down)")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        body_ratio = abs(c0 - o0) / abs(c1 - o1) if abs(c1 - o1) > 0 else 1
        confidence = min(0.82, 0.50 + min(body_ratio, 2) * 0.10 + (len(met) - 3) * 0.05)

        return Signal(
            signal_type="SELL",
            confidence=round(confidence, 4),
            risk_score=0.50,
            expected_upside_pct=0.0,
            stop_loss_pct=0.0,
            target_pct=0.0,
            holding_days=0,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14", "sma_20"]
