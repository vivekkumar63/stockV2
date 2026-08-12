import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkConsecutiveHigherCloses(BaseStrategy):
    """Chartink: Strong Stocks — 5 consecutive days of higher closes with volume confirmation."""
    name = "Consecutive Higher Closes"
    description = "5 straight days of higher closes + volume above average + RSI not overbought"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 12

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 7:
            return Signal("NONE")

        close = df["close"]
        rsi = df["rsi_14"].iloc[-1]
        vol_ratio = df["volume_ratio"].iloc[-1]

        if any(pd.isna(x) for x in [rsi, vol_ratio]):
            return Signal("NONE")

        closes = [float(close.iloc[-i]) for i in range(1, 7)]  # [today, -1, -2, -3, -4, -5]

        consecutive = sum(
            1 for i in range(len(closes) - 1) if closes[i] > closes[i + 1]
        )

        met, failed = [], []

        if consecutive >= 5:
            total_gain = (closes[0] / closes[5] - 1) * 100
            met.append(f"{consecutive} consecutive higher closes (+{total_gain:.1f}% over 5d)")
        else:
            failed.append(f"Only {consecutive}/5 consecutive higher closes")

        if not pd.isna(rsi) and rsi < 75:
            met.append(f"RSI {rsi:.1f} not overbought (< 75)")
        else:
            failed.append(f"RSI {rsi:.1f} overbought (≥ 75)")

        if not pd.isna(vol_ratio) and vol_ratio > 1.0:
            met.append(f"Volume ratio {vol_ratio:.2f}x (above average)")
        else:
            failed.append(f"Low volume ({vol_ratio:.2f}x avg)")

        if len(met) < 2:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        gain_5d = (closes[0] / closes[4] - 1) * 100 if closes[4] > 0 else 0
        confidence = min(0.85, 0.58 + consecutive * 0.04 + min(gain_5d, 5) / 50)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.50,
            expected_upside_pct=7.0,
            stop_loss_pct=4.0,
            target_pct=7.0,
            holding_days=8,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14", "volume_ratio"]
