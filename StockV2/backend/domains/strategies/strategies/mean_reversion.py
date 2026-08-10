import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class MeanReversionStrategy(BaseStrategy):
    name = "Mean Reversion"
    description = "Buy oversold stocks in non-trending markets (close < BB lower, RSI < 40, ADX < 25)"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    weight = 0.15
    min_holding_days = 7
    max_holding_days = 21

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if df.empty or "bb_lower" not in df.columns:
            return Signal("NONE")
        row = df.iloc[-1]
        close = row["close"]
        bb_lower = row["bb_lower"]
        bb_upper = row["bb_upper"]
        rsi = row["rsi_14"]
        adx = row["adx_14"]
        if any(pd.isna(x) for x in [close, bb_lower, bb_upper, rsi, adx]):
            return Signal("NONE")
        if close < bb_lower and rsi < 40 and adx < 25:
            confidence = min(1.0, 0.50 + (40 - rsi) / 80)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.45,
                expected_upside_pct=8.0,
                stop_loss_pct=6.0,
                target_pct=10.0,
                holding_days=12,
                conditions_met=[
                    f"Close {close:.2f} < BB Lower {bb_lower:.2f}",
                    f"RSI={rsi:.1f} < 40",
                    f"ADX={adx:.1f} < 25 (non-trending)",
                ],
            )
        if close > bb_upper and rsi > 70:
            return Signal(
                signal_type="SELL",
                confidence=0.60,
                risk_score=0.55,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=["Close > BB Upper and RSI > 70 (overbought)"],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["bb_lower", "bb_upper", "rsi_14", "adx_14"]
