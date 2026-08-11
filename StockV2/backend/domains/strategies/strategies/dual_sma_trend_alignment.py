import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class DualSMATrendAlignmentStrategy(BaseStrategy):
    name = "Dual SMA Trend Alignment"
    description = "Buy when both SMA20 and SMA50 are rising together — broad trend confirmed across timeframes"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 3:
            return Signal("NONE")

        sma20 = df["sma_20"].iloc[-1]
        prev_sma20 = df["sma_20"].iloc[-2]
        sma50 = df["sma_50"].iloc[-1]
        prev_sma50 = df["sma_50"].iloc[-2]
        close = df["close"].iloc[-1]

        if any(pd.isna(x) for x in [sma20, prev_sma20, sma50, prev_sma50]):
            return Signal("NONE")

        sma20_rising = sma20 > prev_sma20
        sma50_rising = sma50 > prev_sma50
        prev_not_aligned = not (df["sma_20"].iloc[-2] > df["sma_20"].iloc[-3] and
                                df["sma_50"].iloc[-2] > df["sma_50"].iloc[-3]) if len(df) >= 3 else False

        # Signal on the bar where both SMAs align upward together
        just_aligned = sma20_rising and sma50_rising and close > sma20

        # Only fire on the crossover day (avoid re-firing every bar)
        if len(df) >= 3:
            was_aligned = (df["sma_20"].iloc[-2] > df["sma_20"].iloc[-3] and
                           df["sma_50"].iloc[-2] > df["sma_50"].iloc[-3])
            if just_aligned and not was_aligned:
                rsi = df["rsi_14"].iloc[-1]
                rsi_note = f", RSI={rsi:.1f}" if not pd.isna(rsi) else ""
                return Signal(
                    signal_type="BUY",
                    confidence=0.65,
                    risk_score=0.40,
                    expected_upside_pct=14.0,
                    stop_loss_pct=6.0,
                    target_pct=14.0,
                    holding_days=20,
                    conditions_met=[
                        f"SMA20={sma20:.2f} and SMA50={sma50:.2f} both just turned upward{rsi_note}",
                    ],
                )

        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["sma_20", "sma_50"]
