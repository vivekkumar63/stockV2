import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class SMARibbonStrongUptrendStrategy(BaseStrategy):
    name = "SMA Ribbon Strong Uptrend"
    description = "Buy when SMA5 > SMA10 > SMA20 aligns — triple MA bullish stack confirms strong uptrend entry"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        sma5 = df["sma_5"].iloc[-1]
        sma10 = df["sma_10"].iloc[-1]
        sma20 = df["sma_20"].iloc[-1]
        prev5 = df["sma_5"].iloc[-2]
        prev10 = df["sma_10"].iloc[-2]
        prev20 = df["sma_20"].iloc[-2]

        if any(pd.isna(x) for x in [sma5, sma10, sma20, prev5, prev10, prev20]):
            return Signal("NONE")

        now_stacked = sma5 > sma10 > sma20
        was_stacked = prev5 > prev10 > prev20

        # Only fire on the bar the ribbon first aligns
        if now_stacked and not was_stacked:
            rsi = df["rsi_14"].iloc[-1]
            rsi_note = f", RSI={rsi:.1f}" if not pd.isna(rsi) else ""
            return Signal(
                signal_type="BUY",
                confidence=0.66,
                risk_score=0.42,
                expected_upside_pct=12.0,
                stop_loss_pct=5.0,
                target_pct=12.0,
                holding_days=12,
                conditions_met=[
                    f"SMA ribbon just stacked bullish: SMA5={sma5:.2f} > SMA10={sma10:.2f} > SMA20={sma20:.2f}{rsi_note}",
                ],
            )

        # Sell when ribbon inverts
        now_inverted = sma5 < sma10 < sma20
        was_inverted = prev5 < prev10 < prev20
        if now_inverted and not was_inverted:
            return Signal(
                signal_type="SELL",
                confidence=0.64,
                risk_score=0.55,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[f"SMA ribbon inverted bearish: SMA5={sma5:.2f} < SMA10={sma10:.2f} < SMA20={sma20:.2f}"],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["sma_5", "sma_10", "sma_20"]
