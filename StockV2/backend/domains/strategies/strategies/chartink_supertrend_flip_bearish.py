import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkSupertrendFlipBearish(BaseStrategy):
    """Chartink: SuperTrend Flip Bearish — SuperTrend switches from bullish to bearish."""
    name = "Chartink SuperTrend Flip Bearish"
    description = "SuperTrend flips from +1 to -1 (bearish trend start) + RSI < 50 + volume"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 15

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 20:
            return Signal("NONE")

        r = df.iloc[-1]
        r_prev = df.iloc[-2]

        c = float(r["close"])
        st_now = r["supertrend_direction"]
        st_prev = r_prev["supertrend_direction"]
        st_line = r["supertrend"]
        rsi = r["rsi_14"]
        vol_ratio = r["volume_ratio"]
        sma20 = r["sma_20"]

        if any(pd.isna(x) for x in [st_now, st_prev, rsi, vol_ratio]):
            return Signal("NONE")

        met, failed = [], []

        if st_prev == 1.0 and st_now == -1.0:
            met.append(f"SuperTrend flipped BULLISH → BEARISH (fresh sell signal!)")
        elif st_now == -1.0:
            met.append(f"SuperTrend bearish (direction -1)")
        else:
            failed.append(f"SuperTrend still bullish (direction {st_now:.0f})")

        if not pd.isna(st_line) and c < st_line:
            gap_pct = (st_line - c) / c * 100
            met.append(f"Close {c:.1f} below ST line {st_line:.1f} (-{gap_pct:.2f}%)")
        else:
            failed.append(f"Close still above SuperTrend line")

        if rsi < 50:
            met.append(f"RSI {rsi:.1f} < 50 (bearish momentum)")
        else:
            failed.append(f"RSI {rsi:.1f} > 50 (may recover)")

        if vol_ratio > 1.0:
            met.append(f"Volume {vol_ratio:.2f}x (confirming flip)")
        else:
            failed.append(f"Low volume on flip ({vol_ratio:.2f}x)")

        if not pd.isna(sma20) and c < sma20:
            met.append(f"Close {c:.1f} below SMA20 {sma20:.1f} (confirmed breakdown)")
        elif not pd.isna(sma20):
            failed.append(f"Close {c:.1f} still above SMA20 {sma20:.1f}")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        is_fresh_flip = 1 if (st_prev == 1.0 and st_now == -1.0) else 0
        confidence = min(0.85, 0.55 + is_fresh_flip * 0.12 + (len(met) - 3) * 0.05)

        return Signal(
            signal_type="SELL",
            confidence=round(confidence, 4),
            risk_score=0.45,
            expected_upside_pct=0.0,
            stop_loss_pct=0.0,
            target_pct=0.0,
            holding_days=0,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["supertrend", "supertrend_direction", "rsi_14", "volume_ratio", "sma_20"]
