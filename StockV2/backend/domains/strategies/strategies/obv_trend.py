import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class OBVTrendStrategy(BaseStrategy):
    name = "OBV Trend Confirmation"
    description = "Buy when OBV is above its 10-period SMA and price is above SMA20 (volume confirms trend)"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        obv = df["obv"].iloc[-1]
        obv_prev = df["obv"].iloc[-2]
        obv_sma = df["obv_sma_10"].iloc[-1]
        close = df["close"].iloc[-1]
        sma20 = df["sma_20"].iloc[-1]
        rsi = df["rsi_14"].iloc[-1]

        if any(pd.isna(x) for x in [obv, obv_sma, close, sma20]):
            return Signal("NONE")

        # OBV crosses above its SMA10 while price is above SMA20
        prev_obv_sma = df["obv_sma_10"].iloc[-2]
        if pd.isna(prev_obv_sma):
            return Signal("NONE")

        obv_crossed_up = obv_prev <= prev_obv_sma and obv > obv_sma
        price_above_ma = close > sma20

        if obv_crossed_up and price_above_ma:
            rsi_note = f", RSI={rsi:.1f}" if not pd.isna(rsi) else ""
            return Signal(
                signal_type="BUY",
                confidence=0.63,
                risk_score=0.42,
                expected_upside_pct=12.0,
                stop_loss_pct=6.0,
                target_pct=12.0,
                holding_days=15,
                conditions_met=[
                    "OBV crossed above OBV SMA10",
                    f"Price={close:.2f} above SMA20={sma20:.2f}{rsi_note}",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["obv", "obv_sma_10", "sma_20"]
