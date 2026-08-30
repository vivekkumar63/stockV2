"""
UT Bot Alerts (by Keevenv)

ATR Trailing Stop (key=1.0, ATR14) + HMA(50) trend filter.
BUY when close crosses ABOVE the trailing stop while above HMA(50).
"""
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class UTBotStrategy(BaseStrategy):
    name = "UT Bot"
    description = (
        "ATR trailing stop that flips on close-side crosses, filtered by HMA(50) uptrend. "
        "BUY when price crosses above the trailing stop in an uptrend."
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe     = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 15
    weight           = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["close", "hma_50", "ut_bot_stop"]
        if len(df) < 56 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        c_now   = float(df["close"].iloc[-1])
        c_prev  = float(df["close"].iloc[-2])
        ts_now  = float(df["ut_bot_stop"].iloc[-1])
        ts_prev = float(df["ut_bot_stop"].iloc[-2])
        hma_now = float(df["hma_50"].iloc[-1])

        if any(pd.isna(x) for x in [ts_now, ts_prev, hma_now]):
            return Signal(signal_type="NONE", conditions_failed=["Indicators not ready"])

        crossed_above = c_prev <= ts_prev and c_now > ts_now
        above_hma     = c_now > hma_now

        conditions_met    = []
        conditions_failed = []

        if crossed_above:
            conditions_met.append(f"Price crossed above ATR trailing stop ({ts_now:.2f})")
        else:
            gap = ((c_now - ts_now) / ts_now) * 100
            conditions_failed.append(f"No crossover (price {gap:+.1f}% vs trailing stop)")

        if above_hma:
            conditions_met.append(f"Price {c_now:.2f} above HMA(50)={hma_now:.2f}")
        else:
            conditions_failed.append(f"Price below HMA(50)={hma_now:.2f}")

        if crossed_above and above_hma:
            gap_pct = ((c_now - ts_now) / ts_now) * 100
            confidence = round(min(0.62 + gap_pct * 0.02, 0.88), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.32,
                expected_upside_pct=9.0,
                stop_loss_pct=5.0,
                target_pct=9.0,
                holding_days=10,
                conditions_met=conditions_met,
            )

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed)

    def get_required_indicators(self) -> list[str]:
        return ["close", "hma_50", "ut_bot_stop"]
