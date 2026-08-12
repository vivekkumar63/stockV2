import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkMomentumPDH(BaseStrategy):
    """Chartink: Bullish Momentum — close breaks above previous day's high with SMA trend + RSI."""
    name = "Momentum PDH Breakout"
    description = "Close > previous day high + SMA20>SMA50 + RSI>50 + above-average volume"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 10

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 52:
            return Signal("NONE")

        c = float(df["close"].iloc[-1])
        prev_high = float(df["high"].iloc[-2])
        rsi = df["rsi_14"].iloc[-1]
        sma20 = df["sma_20"].iloc[-1]
        sma50 = df["sma_50"].iloc[-1]
        vol_ratio = df["volume_ratio"].iloc[-1]

        if any(pd.isna(x) for x in [rsi, sma20, sma50, vol_ratio]):
            return Signal("NONE")

        met, failed = [], []

        if c > prev_high:
            met.append(f"Close {c:.1f} > prev day high {prev_high:.1f} (PDH breakout)")
        else:
            failed.append(f"Close {c:.1f} not above prev high {prev_high:.1f}")

        if rsi > 50:
            met.append(f"RSI {rsi:.1f} > 50 (momentum bullish)")
        else:
            failed.append(f"RSI {rsi:.1f} < 50")

        if sma20 > sma50:
            met.append(f"SMA20 {sma20:.1f} > SMA50 {sma50:.1f} (trend aligned)")
        else:
            failed.append(f"SMA20 < SMA50 (downtrend)")

        if c > sma50:
            met.append(f"Close above SMA50 ({sma50:.1f})")
        else:
            failed.append(f"Close below SMA50")

        if vol_ratio > 1.0:
            met.append(f"Volume ratio {vol_ratio:.2f}x (above average)")
        else:
            failed.append(f"Volume below average ({vol_ratio:.2f}x)")

        if len(met) < 4:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        breakout_pct = (c / prev_high - 1) * 100
        rsi_boost = max(0.0, (rsi - 50) / 50 * 0.15)
        confidence = min(0.90, 0.60 + breakout_pct / 10 + rsi_boost)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.42,
            expected_upside_pct=8.0,
            stop_loss_pct=4.0,
            target_pct=8.0,
            holding_days=7,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14", "sma_20", "sma_50", "volume_ratio"]
