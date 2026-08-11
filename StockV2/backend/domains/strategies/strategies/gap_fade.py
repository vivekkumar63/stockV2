import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class GapFadeStrategy(BaseStrategy):
    name = "Gap Fade"
    description = "Buy when stock gaps down 0.5%-4% at open, expecting mean reversion"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 2:
            return Signal("NONE")

        gap = df["gap_pct"].iloc[-1]
        rsi = df["rsi_14"].iloc[-1]
        vol_ratio = df["volume_ratio"].iloc[-1]

        if pd.isna(gap) or pd.isna(rsi):
            return Signal("NONE")

        # Gap down between 0.5% and 4% — large gaps often continue down
        if -4.0 <= gap <= -0.5 and rsi > 25:
            vol_note = f", vol_ratio={vol_ratio:.2f}" if not pd.isna(vol_ratio) else ""
            return Signal(
                signal_type="BUY",
                confidence=0.60,
                risk_score=0.45,
                expected_upside_pct=8.0,
                stop_loss_pct=5.0,
                target_pct=8.0,
                holding_days=5,
                conditions_met=[f"Gap down {gap:.2f}%, RSI={rsi:.1f}{vol_note}"],
            )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["gap_pct", "rsi_14", "volume_ratio"]
