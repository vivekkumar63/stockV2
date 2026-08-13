import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkPerfectSell(BaseStrategy):
    """Chartink: Perfect Sell — lower high reversal after upswing, entry open, SL prev high."""
    name = "Chartink Perfect Sell Reversal"
    description = "Prev high > 2d-ago high + today lower high + volume surge = bearish reversal"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 1
    max_holding_days = 5

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 5:
            return Signal("NONE")

        c = float(df["close"].iloc[-1])
        h0 = float(df["high"].iloc[-1])
        h1 = float(df["high"].iloc[-2])
        h2 = float(df["high"].iloc[-3])
        v0 = float(df["volume"].iloc[-1])
        v3 = float(df["volume"].iloc[-4])
        rsi = df["rsi_14"].iloc[-1]

        met, failed = [], []

        # Condition 1: Previous day's high > 2 days ago high (was making higher highs)
        if h1 > h2:
            met.append(f"Prev high {h1:.1f} > 2d-ago high {h2:.1f} (prior upswing)")
        else:
            failed.append(f"No prior upswing ({h1:.1f} ≤ {h2:.1f})")

        # Condition 2: Today's high < yesterday's high (lower high formed)
        if h0 < h1:
            met.append(f"Today's high {h0:.1f} < prev high {h1:.1f} (lower high)")
        else:
            failed.append(f"New high today ({h0:.1f} ≥ {h1:.1f})")

        # Condition 3: Today's close < yesterday's high (confirmed reversal)
        if c < h1:
            met.append(f"Close {c:.1f} < prev high {h1:.1f} (reversal confirmed)")
        else:
            failed.append(f"Close {c:.1f} above prev high")

        # Condition 4: Volume expanding (more sellers entering)
        if v3 > 0 and v0 > v3:
            met.append(f"Volume {v0:,.0f} > 3d-ago {v3:,.0f} (expanding)")
        else:
            failed.append(f"Volume not expanding")

        # Extra: RSI turning down from high level
        if not pd.isna(rsi) and rsi > 55:
            met.append(f"RSI {rsi:.1f} > 55 (reversing from high)")
        elif not pd.isna(rsi):
            failed.append(f"RSI {rsi:.1f} already low")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        reversal_pct = (h1 - c) / h1 * 100
        confidence = min(0.85, 0.55 + reversal_pct / 10 + (len(met) - 3) * 0.05)

        return Signal(
            signal_type="SELL",
            confidence=round(confidence, 4),
            risk_score=0.55,
            expected_upside_pct=0.0,
            stop_loss_pct=0.0,
            target_pct=0.0,
            holding_days=0,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14"]
