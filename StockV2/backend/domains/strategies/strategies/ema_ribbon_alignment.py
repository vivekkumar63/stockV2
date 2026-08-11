import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class EMARibbonAlignmentStrategy(BaseStrategy):
    name = "EMA Ribbon Alignment"
    description = "Buy when all EMAs are stacked bullish (EMA5 > EMA10 > EMA21) — multi-timeframe trend confirmation"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        ema5 = df["ema_5"].iloc[-1]
        ema10 = df["ema_10"].iloc[-1]
        ema21 = df["ema_21"].iloc[-1]
        prev_ema5 = df["ema_5"].iloc[-2]
        prev_ema10 = df["ema_10"].iloc[-2]
        prev_ema21 = df["ema_21"].iloc[-2]

        if any(pd.isna(x) for x in [ema5, ema10, ema21, prev_ema5, prev_ema10, prev_ema21]):
            return Signal("NONE")

        now_bullish = ema5 > ema10 > ema21
        was_not_aligned = not (prev_ema5 > prev_ema10 > prev_ema21)

        # Signal only on the crossover day (ribbon just aligned)
        if now_bullish and was_not_aligned:
            rsi = df["rsi_14"].iloc[-1]
            rsi_note = f", RSI={rsi:.1f}" if not pd.isna(rsi) else ""
            return Signal(
                signal_type="BUY",
                confidence=0.67,
                risk_score=0.43,
                expected_upside_pct=14.0,
                stop_loss_pct=6.0,
                target_pct=14.0,
                holding_days=18,
                conditions_met=[
                    f"EMA ribbon just aligned bullish: EMA5={ema5:.2f} > EMA10={ema10:.2f} > EMA21={ema21:.2f}{rsi_note}",
                ],
            )

        # Sell signal: ribbon just aligned bearish
        now_bearish = ema5 < ema10 < ema21
        was_not_bearish = not (prev_ema5 < prev_ema10 < prev_ema21)
        if now_bearish and was_not_bearish:
            return Signal(
                signal_type="SELL",
                confidence=0.65,
                risk_score=0.55,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[f"EMA ribbon just aligned bearish: EMA5={ema5:.2f} < EMA10={ema10:.2f} < EMA21={ema21:.2f}"],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["ema_5", "ema_10", "ema_21"]
