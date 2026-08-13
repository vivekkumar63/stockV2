import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkSupertrendFlip(BaseStrategy):
    """Chartink: SuperTrend Flip — SuperTrend switches from bearish to bullish, fresh trend start."""
    name = "Chartink SuperTrend Flip Bullish"
    description = "SuperTrend flips from -1 to +1 (trend reversal) + RSI > 50 + volume confirmation"
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
        macd = r["macd"]
        macd_sig = r["macd_signal"]

        if any(pd.isna(x) for x in [st_now, st_prev, rsi, vol_ratio]):
            return Signal("NONE")

        met, failed = [], []

        if st_prev == -1.0 and st_now == 1.0:
            met.append(f"SuperTrend flipped BEARISH → BULLISH (fresh signal!)")
        elif st_now == 1.0:
            met.append(f"SuperTrend bullish (direction +1)")
        else:
            failed.append(f"SuperTrend still bearish (direction {st_now:.0f})")

        if not pd.isna(st_line) and c > st_line:
            gap_pct = (c - st_line) / st_line * 100
            met.append(f"Close {c:.1f} above ST line {st_line:.1f} (+{gap_pct:.2f}%)")
        else:
            failed.append(f"Close below SuperTrend line")

        if rsi > 50:
            met.append(f"RSI {rsi:.1f} > 50 (bullish momentum)")
        else:
            failed.append(f"RSI {rsi:.1f} < 50")

        if vol_ratio > 1.0:
            met.append(f"Volume {vol_ratio:.2f}x (confirming flip)")
        else:
            failed.append(f"Low volume on flip ({vol_ratio:.2f}x)")

        if not pd.isna(macd) and not pd.isna(macd_sig) and macd > macd_sig:
            met.append(f"MACD {macd:.3f} > signal {macd_sig:.3f} (aligned)")
        elif not pd.isna(macd) and not pd.isna(macd_sig):
            failed.append(f"MACD still bearish ({macd:.3f} < {macd_sig:.3f})")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        is_fresh_flip = 1 if (st_prev == -1.0 and st_now == 1.0) else 0
        confidence = min(0.88, 0.58 + is_fresh_flip * 0.12 + (len(met) - 3) * 0.05)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.40,
            expected_upside_pct=10.0,
            stop_loss_pct=4.0,
            target_pct=10.0,
            holding_days=10,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["supertrend", "supertrend_direction", "rsi_14", "volume_ratio", "macd", "macd_signal"]
