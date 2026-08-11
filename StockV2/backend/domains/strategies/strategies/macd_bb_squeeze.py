import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class MACDBBSqueezeStrategy(BaseStrategy):
    name = "MACD + BB Squeeze"
    description = "Buy when MACD turns bullish while Bollinger Bands are squeezing (pre-breakout setup)"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        macd = df["macd"].iloc[-1]
        macd_signal = df["macd_signal"].iloc[-1]
        macd_prev = df["macd"].iloc[-2]
        macd_signal_prev = df["macd_signal"].iloc[-2]
        bb_width = df["bb_width"].iloc[-1]
        bb_width_avg = df["bb_width_sma_20"].iloc[-1]

        if any(pd.isna(x) for x in [macd, macd_signal, macd_prev, macd_signal_prev, bb_width, bb_width_avg]):
            return Signal("NONE")

        # MACD crosses above signal line while BB is squeezing
        macd_crossed_up = macd_prev <= macd_signal_prev and macd > macd_signal
        squeezing = bb_width < bb_width_avg

        if macd_crossed_up and squeezing:
            rsi = df["rsi_14"].iloc[-1]
            rsi_note = f", RSI={rsi:.1f}" if not pd.isna(rsi) else ""
            return Signal(
                signal_type="BUY",
                confidence=0.68,
                risk_score=0.44,
                expected_upside_pct=14.0,
                stop_loss_pct=6.5,
                target_pct=14.0,
                holding_days=15,
                conditions_met=[
                    f"MACD={macd:.4f} crossed above signal={macd_signal:.4f}",
                    f"BB squeezing (width={bb_width:.4f} < avg={bb_width_avg:.4f}){rsi_note}",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["macd", "macd_signal", "bb_width", "bb_width_sma_20"]
