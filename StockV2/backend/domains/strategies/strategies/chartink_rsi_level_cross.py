import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkRSILevelCross(BaseStrategy):
    """Chartink: Daily RSI Crossover — RSI crosses above 60 (momentum buy) or below 40 (momentum sell)."""
    name = "RSI Level Crossover"
    description = "BUY when RSI(14) crosses above 60; SELL when crosses below 40"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 15

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 16:
            return Signal("NONE")

        rsi = df["rsi_14"].iloc[-1]
        rsi_prev = df["rsi_14"].iloc[-2]
        macd_hist = df["macd_hist"].iloc[-1]

        if any(pd.isna(x) for x in [rsi, rsi_prev]):
            return Signal("NONE")

        # BUY: RSI crossed above 60 — momentum breakout into strong territory
        if rsi_prev < 60 and rsi >= 60:
            met = [f"RSI {rsi:.1f} crossed above 60 (momentum breakout)"]
            failed = []
            if not pd.isna(macd_hist) and macd_hist > 0:
                met.append(f"MACD histogram positive ({macd_hist:.3f})")
            else:
                failed.append("MACD histogram not confirming")
            confidence = min(0.88, 0.62 + (rsi - 60) / 30 * 0.25)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.45,
                expected_upside_pct=10.0,
                stop_loss_pct=5.0,
                target_pct=10.0,
                holding_days=10,
                conditions_met=met,
                conditions_failed=failed,
            )

        # SELL: RSI crossed below 40 — momentum breakdown
        if rsi_prev > 40 and rsi <= 40:
            met = [f"RSI {rsi:.1f} crossed below 40 (momentum breakdown)"]
            failed = []
            if not pd.isna(macd_hist) and macd_hist < 0:
                met.append(f"MACD histogram negative ({macd_hist:.3f})")
            else:
                failed.append("MACD not confirming")
            confidence = min(0.85, 0.60 + (40 - rsi) / 30 * 0.25)
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

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14", "macd_hist"]
