import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class Chartink5DayRangeBreakout(BaseStrategy):
    """Chartink: 5-Day Range Breakout — close above 5-day consolidation high with volume surge."""
    name = "5-Day Range Breakout"
    description = "Close > 5-day high on volume surge + RSI bullish + MACD confirmation"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 2
    max_holding_days = 8

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 22:
            return Signal("NONE")

        r = df.iloc[-1]
        c = float(r["close"])
        rsi = r["rsi_14"]
        vol_ratio = r["volume_ratio"]
        macd = r["macd"]
        macd_sig = r["macd_signal"]
        sma20 = r["sma_20"]

        if any(pd.isna(x) for x in [rsi, vol_ratio]):
            return Signal("NONE")

        high_5d = float(df["high"].iloc[-6:-1].max())
        low_5d = float(df["low"].iloc[-6:-1].min())
        range_5d = high_5d - low_5d

        met, failed = [], []

        if c > high_5d:
            breakout_pct = (c - high_5d) / high_5d * 100
            met.append(f"Close {c:.1f} broke above 5-day high {high_5d:.1f} (+{breakout_pct:.2f}%)")
        else:
            failed.append(f"Close {c:.1f} still below 5-day high {high_5d:.1f}")

        consolidation_pct = range_5d / high_5d * 100
        if consolidation_pct < 5.0:
            met.append(f"5-day range tight ({consolidation_pct:.1f}%) — coiled spring")
        else:
            failed.append(f"5-day range wide ({consolidation_pct:.1f}%), not a tight coil")

        if vol_ratio > 1.5:
            met.append(f"Strong breakout volume {vol_ratio:.2f}x")
        elif vol_ratio > 1.0:
            met.append(f"Above-average volume {vol_ratio:.2f}x")
        else:
            failed.append(f"Breakout on weak volume ({vol_ratio:.2f}x)")

        if rsi > 50:
            met.append(f"RSI {rsi:.1f} > 50 (bullish momentum)")
        else:
            failed.append(f"RSI {rsi:.1f} < 50")

        if not pd.isna(macd) and not pd.isna(macd_sig) and macd > macd_sig:
            met.append(f"MACD {macd:.3f} > signal {macd_sig:.3f}")
        elif not pd.isna(macd) and not pd.isna(macd_sig):
            failed.append(f"MACD bearish ({macd:.3f} < {macd_sig:.3f})")

        if not pd.isna(sma20) and c > sma20:
            met.append(f"Close {c:.1f} above SMA20 {sma20:.1f}")
        elif not pd.isna(sma20):
            failed.append(f"Close {c:.1f} below SMA20 {sma20:.1f}")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        breakout_pct = (c - high_5d) / high_5d * 100 if c > high_5d else 0
        confidence = min(0.85, 0.55 + breakout_pct / 10 + (len(met) - 3) * 0.04)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.40,
            expected_upside_pct=6.0,
            stop_loss_pct=3.0,
            target_pct=6.0,
            holding_days=5,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14", "volume_ratio", "macd", "macd_signal", "sma_20"]
