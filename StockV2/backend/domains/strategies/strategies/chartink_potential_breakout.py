import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkPotentialBreakout(BaseStrategy):
    """Chartink: Potential Breakouts — consolidating within 5% of 200-day high, volume surging."""
    name = "Chartink Potential Breakout"
    description = "Close within 5% below 200-day high + 30-day consolidation + above-average volume"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 5
    max_holding_days = 20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 50:
            return Signal("NONE")

        close = df["close"]
        high = df["high"]
        volume = df["volume"]
        c = close.iloc[-1]
        v = float(volume.iloc[-1])

        lookback_200 = min(200, len(df))
        max_200d_high = float(high.iloc[-lookback_200:].max())
        vol_sma20 = df["volume_sma_20"].iloc[-1]

        met, failed = [], []

        # Condition 1: Close is within 5% below the multi-month high
        if c * 1.05 >= max_200d_high and c >= 100:
            gap_pct = (max_200d_high - c) / max_200d_high * 100
            met.append(f"Within {gap_pct:.1f}% of {lookback_200}d high {max_200d_high:.1f}")
        else:
            failed.append(f"Not near {lookback_200}d high (close {c:.1f} vs {max_200d_high:.1f})")

        # Condition 2: Consolidation — 30-day high not making new recent highs
        if len(df) >= 38:
            max_30d_now = float(high.iloc[-30:].max())
            max_8d_prior = float(high.iloc[-38:-30].max())
            if max_30d_now <= max_8d_prior * 1.02:
                met.append(f"Consolidating (30d high {max_30d_now:.1f} ≤ prior {max_8d_prior:.1f})")
            else:
                failed.append("No consolidation — making new recent highs")
        else:
            failed.append("Insufficient history for consolidation check")

        # Condition 3: Volume above average
        if not pd.isna(vol_sma20) and vol_sma20 > 0 and v > vol_sma20:
            met.append(f"Volume {v:,.0f} > 20d avg {vol_sma20:,.0f}")
        else:
            failed.append("Volume below 20-day average")

        if len(met) < 2:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        # Confidence based on proximity to breakout level
        proximity = c / max_200d_high  # 0.95+ = very close
        confidence = min(0.88, 0.55 + proximity * 0.35)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.40,
            expected_upside_pct=10.0,
            stop_loss_pct=5.0,
            target_pct=10.0,
            holding_days=15,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["close", "high", "volume_sma_20"]
