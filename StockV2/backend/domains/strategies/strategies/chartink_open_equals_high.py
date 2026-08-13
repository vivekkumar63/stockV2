import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkOpenEqualsHigh(BaseStrategy):
    """Chartink: SELL Open=High — open equals day's high, full bearish candle from open."""
    name = "Chartink Open = High Bearish"
    description = "Open == High (no early buying) + red candle + volume + RSI not oversold"
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
        if abs(h - o) <= tol:
            met.append(f"Open {o:.2f} ≈ High {h:.2f} (no early buying)")
        else:
            failed.append(f"High {h:.2f} > Open {o:.2f} by {h - o:.2f}")

        if c < o:
            body_pct = (o - c) / o * 100
            met.append(f"Red candle -{body_pct:.2f}% from open")
        else:
            failed.append(f"Not a red candle (close {c:.2f} ≥ open {o:.2f})")

        if vol_ratio > 1.0:
            met.append(f"Volume {vol_ratio:.2f}x above average (selling pressure)")
        else:
            failed.append(f"Low volume ({vol_ratio:.2f}x avg)")

        if rsi > 30:
            met.append(f"RSI {rsi:.1f} not oversold (> 30)")
        else:
            failed.append(f"RSI {rsi:.1f} oversold (≤ 30), may bounce")

        if lo < o * 0.995:
            met.append(f"Meaningful range L {lo:.2f} (-{(1 - lo/o)*100:.2f}%)")
        else:
            failed.append(f"Negligible range ({(1 - lo/o)*100:.2f}%)")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        body_pct = (o - c) / o * 100
        confidence = min(0.82, 0.52 + body_pct / 20 + (len(met) - 3) * 0.05)

        return Signal(
            signal_type="SELL",
            confidence=round(confidence, 4),
            risk_score=0.50,
            expected_upside_pct=0.0,
            stop_loss_pct=0.0,
            target_pct=0.0,
            holding_days=0,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14", "volume_ratio"]
