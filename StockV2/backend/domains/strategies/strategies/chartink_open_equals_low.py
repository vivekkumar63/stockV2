import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkOpenEqualsLow(BaseStrategy):
    """Chartink: BUY Open=Low — open equals day's low, full bullish candle from open."""
    name = "Open = Low Bullish"
    description = "Open == Low (no early selling) + green candle + volume + RSI not overbought"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 1
    max_holding_days = 4

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 20:
            return Signal("NONE")

        r = df.iloc[-1]
        o = float(r["open"])
        h = float(r["high"])
        lo = float(r["low"])
        c = float(r["close"])
        rsi = r["rsi_14"]
        vol_ratio = r["volume_ratio"]

        if any(pd.isna(x) for x in [rsi, vol_ratio]):
            return Signal("NONE")

        met, failed = [], []

        tol = max(o * 0.001, 0.05)
        if abs(o - lo) <= tol:
            met.append(f"Open {o:.2f} ≈ Low {lo:.2f} (no early selling)")
        else:
            failed.append(f"Open {o:.2f} > Low {lo:.2f} by {o - lo:.2f}")

        if c > o:
            body_pct = (c - o) / o * 100
            met.append(f"Green candle +{body_pct:.2f}% from open")
        else:
            failed.append(f"Not a green candle (close {c:.2f} ≤ open {o:.2f})")

        if vol_ratio > 1.0:
            met.append(f"Volume {vol_ratio:.2f}x above average")
        else:
            failed.append(f"Low volume ({vol_ratio:.2f}x avg)")

        if rsi < 75:
            met.append(f"RSI {rsi:.1f} not overbought (< 75)")
        else:
            failed.append(f"RSI {rsi:.1f} overbought (≥ 75)")

        if h > o * 1.005:
            met.append(f"Meaningful range H {h:.2f} (+{(h/o-1)*100:.2f}%)")
        else:
            failed.append(f"Negligible range ({(h/o-1)*100:.2f}%)")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        body_pct = (c - o) / o * 100
        confidence = min(0.85, 0.55 + body_pct / 20 + (len(met) - 3) * 0.05)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.45,
            expected_upside_pct=4.0,
            stop_loss_pct=2.0,
            target_pct=4.0,
            holding_days=2,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14", "volume_ratio"]
