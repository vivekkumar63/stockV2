import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class PriceSMA50BounceStrategy(BaseStrategy):
    name = "SMA50 Support Bounce"
    description = "Buy when price dips to within 2% of SMA50 and closes back above it — key support level bounce"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        close = df["close"].iloc[-1]
        prev_close = df["close"].iloc[-2]
        sma50 = df["sma_50"].iloc[-1]
        rsi = df["rsi_14"].iloc[-1]

        if any(pd.isna(x) for x in [close, prev_close, sma50]):
            return Signal("NONE")

        # Previous bar touched/breached SMA50, current bar closes back above
        prev_near_or_below = prev_close <= sma50 * 1.02
        curr_above = close > sma50

        if prev_near_or_below and curr_above:
            bounce_pct = (close - sma50) / sma50 * 100
            rsi_note = f", RSI={rsi:.1f}" if not pd.isna(rsi) else ""
            return Signal(
                signal_type="BUY",
                confidence=0.64,
                risk_score=0.41,
                expected_upside_pct=10.0,
                stop_loss_pct=5.0,
                target_pct=10.0,
                holding_days=12,
                conditions_met=[
                    f"Price bounced off SMA50={sma50:.2f} → now {close:.2f} (+{bounce_pct:.1f}% above){rsi_note}",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["sma_50", "rsi_14"]
