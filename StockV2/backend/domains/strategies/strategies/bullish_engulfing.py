import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class BullishEngulfingStrategy(BaseStrategy):
    name = "Bullish Engulfing"
    description = "Buy when a large green candle fully engulfs the previous red candle with volume confirmation"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 3:
            return Signal("NONE")

        curr = df.iloc[-1]
        prev = df.iloc[-2]
        rsi = df["rsi_14"].iloc[-1]

        curr_body_size = abs(curr["close"] - curr["open"])
        prev_body_size = abs(prev["close"] - prev["open"])

        if any(pd.isna(x) for x in [curr_body_size, prev_body_size]):
            return Signal("NONE")

        # Previous candle must be red, current must be green and engulf previous body
        prev_red = prev["close"] < prev["open"]
        curr_green = curr["close"] > curr["open"]
        engulfs = curr["open"] <= prev["close"] and curr["close"] >= prev["open"]

        # Body size confirmation: current body > previous body
        larger_body = curr_body_size > prev_body_size * 0.8

        if prev_red and curr_green and engulfs and larger_body:
            rsi_note = f", RSI={rsi:.1f}" if not pd.isna(rsi) else ""
            vol_ratio = df["volume_ratio"].iloc[-1]
            vol_note = f", Vol={vol_ratio:.1f}x" if not pd.isna(vol_ratio) else ""
            return Signal(
                signal_type="BUY",
                confidence=0.64,
                risk_score=0.43,
                expected_upside_pct=9.0,
                stop_loss_pct=5.0,
                target_pct=9.0,
                holding_days=7,
                conditions_met=[
                    f"Bullish engulfing: {curr['open']:.2f}→{curr['close']:.2f} engulfs {prev['open']:.2f}→{prev['close']:.2f}{rsi_note}{vol_note}",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["volume_ratio", "rsi_14"]
