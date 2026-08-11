import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class SuperTrendADXConfirmedStrategy(BaseStrategy):
    name = "SuperTrend + ADX Confirmed"
    description = "Buy when SuperTrend is bullish AND ADX > 25 — trend confirmed by both direction and strength"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        st_dir = df["supertrend_direction"].iloc[-1]
        prev_dir = df["supertrend_direction"].iloc[-2]
        adx = df["adx_14"].iloc[-1]

        if any(pd.isna(x) for x in [st_dir, prev_dir, adx]):
            return Signal("NONE")

        # SuperTrend flips bullish AND ADX confirms trend is strong
        flipped_bullish = prev_dir == -1.0 and st_dir == 1.0
        trend_confirmed = adx > 25

        if flipped_bullish and trend_confirmed:
            rsi = df["rsi_14"].iloc[-1]
            rsi_note = f", RSI={rsi:.1f}" if not pd.isna(rsi) else ""
            return Signal(
                signal_type="BUY",
                confidence=0.72,
                risk_score=0.40,
                expected_upside_pct=18.0,
                stop_loss_pct=7.0,
                target_pct=18.0,
                holding_days=25,
                conditions_met=[
                    "SuperTrend flipped bullish",
                    f"ADX={adx:.1f} > 25 (confirmed trend){rsi_note}",
                ],
            )

        # Bearish flip with confirmed trend
        flipped_bearish = prev_dir == 1.0 and st_dir == -1.0
        if flipped_bearish and trend_confirmed:
            return Signal(
                signal_type="SELL",
                confidence=0.70,
                risk_score=0.55,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[
                    "SuperTrend flipped bearish",
                    f"ADX={adx:.1f} > 25 (confirmed trend)",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["supertrend_direction", "adx_14"]
