import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class OBVDivergenceSellStrategy(BaseStrategy):
    name = "OBV Bearish Divergence"
    description = "Sell when OBV is falling while price is rising — volume not confirming the move"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 6:
            return Signal("NONE")

        # Compare current 3-bar OBV trend vs 3-bar price trend
        obv_now = df["obv"].iloc[-1]
        obv_3ago = df["obv"].iloc[-4]
        close_now = df["close"].iloc[-1]
        close_3ago = df["close"].iloc[-4]
        rsi = df["rsi_14"].iloc[-1]

        if any(pd.isna(x) for x in [obv_now, obv_3ago, close_now, close_3ago]):
            return Signal("NONE")

        price_rising = close_now > close_3ago * 1.01   # price up >1%
        obv_falling = obv_now < obv_3ago               # OBV declining

        if price_rising and obv_falling and (pd.isna(rsi) or rsi > 60):
            price_chg = (close_now - close_3ago) / close_3ago * 100
            obv_chg = (obv_now - obv_3ago) / max(abs(obv_3ago), 1) * 100
            return Signal(
                signal_type="SELL",
                confidence=0.62,
                risk_score=0.52,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[
                    f"Price +{price_chg:.1f}% but OBV {obv_chg:.1f}% (bearish divergence)",
                    f"RSI={rsi:.1f}" if not pd.isna(rsi) else "RSI unavailable",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["obv", "rsi_14"]
