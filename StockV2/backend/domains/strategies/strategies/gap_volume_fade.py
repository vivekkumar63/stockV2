import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class GapVolumeFadeStrategy(BaseStrategy):
    name = "Gap + Volume Fade"
    description = "Fade gap when volume spike confirms exhaustion — buy gap-down on high volume, sell gap-up on high volume"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        gap = df["gap_pct"].iloc[-1]
        vol_ratio = df["volume_ratio"].iloc[-1]
        rsi = df["rsi_14"].iloc[-1]

        if any(pd.isna(x) for x in [gap, vol_ratio]):
            return Signal("NONE")

        high_volume = vol_ratio >= 1.8

        # Gap down + high volume = panic selling → fade (BUY)
        if gap <= -1.0 and high_volume and (pd.isna(rsi) or rsi < 50):
            return Signal(
                signal_type="BUY",
                confidence=0.63,
                risk_score=0.46,
                expected_upside_pct=8.0,
                stop_loss_pct=5.0,
                target_pct=8.0,
                holding_days=5,
                conditions_met=[
                    f"Gap down {gap:.1f}% with {vol_ratio:.1f}x volume (panic fade)",
                ],
            )

        # Gap up + high volume = euphoria buying → fade (SELL)
        if gap >= 1.0 and high_volume and (pd.isna(rsi) or rsi > 60):
            return Signal(
                signal_type="SELL",
                confidence=0.61,
                risk_score=0.52,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=[
                    f"Gap up {gap:.1f}% with {vol_ratio:.1f}x volume (euphoria fade)",
                ],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["gap_pct", "volume_ratio", "rsi_14"]
