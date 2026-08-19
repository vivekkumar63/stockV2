import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_MAX_ADX = 25.0   # above this → trending, not ranging
_RSI_OVERSOLD = 35.0
_RSI_OVERBOUGHT = 70.0


class MeanReversionStrategy(BaseStrategy):
    name = "Mean Reversion"
    description = "Buy oversold price below BB lower in ranging market; sell overbought above BB upper"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    weight = 0.12
    min_holding_days = 3
    max_holding_days = 10

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 1:
            return Signal("NONE")
        for col in ("close", "bb_lower", "bb_upper", "rsi_14", "adx_14"):
            if col not in df.columns:
                return Signal("NONE")
        row = df.iloc[-1]
        close = row["close"]
        bb_lower = row["bb_lower"]
        bb_upper = row["bb_upper"]
        rsi = row["rsi_14"]
        adx = row["adx_14"]
        if any(pd.isna(x) for x in [close, bb_lower, bb_upper, rsi, adx]):
            return Signal("NONE")
        if adx > _MAX_ADX:
            return Signal("NONE")
        if close < bb_lower and rsi < _RSI_OVERSOLD:
            return Signal(
                signal_type="BUY",
                confidence=0.65,
                risk_score=0.40,
                stop_loss_pct=5.0,
                target_pct=8.0,
                holding_days=7,
                conditions_met=[
                    f"Price {close:.2f} below BB lower {bb_lower:.2f}",
                    f"RSI {rsi:.1f} oversold",
                    f"ADX {adx:.1f} non-trending",
                ],
            )
        if close > bb_upper and rsi > _RSI_OVERBOUGHT:
            return Signal(
                signal_type="SELL",
                confidence=0.65,
                conditions_met=[
                    f"Price {close:.2f} above BB upper {bb_upper:.2f}",
                    f"RSI {rsi:.1f} overbought",
                ],
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["bb_lower", "bb_upper", "rsi_14", "adx_14"]
