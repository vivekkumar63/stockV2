import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkDojiReversal(BaseStrategy):
    """Chartink: Doji Pattern — indecision candle after trend, often signals reversal."""
    name = "Doji Reversal Pattern"
    description = "Body < 10% of range (Doji) after downtrend with RSI support + next-day confirmation"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 1
    max_holding_days = 5

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 22:
            return Signal("NONE")

        r = df.iloc[-1]
        r_prev = df.iloc[-2]

        o = float(r["open"])
        h = float(r["high"])
        lo = float(r["low"])
        c = float(r["close"])
        rsi = r["rsi_14"]
        sma20 = r["sma_20"]
        vol_ratio = r["volume_ratio"]

        if any(pd.isna(x) for x in [rsi, sma20, vol_ratio]):
            return Signal("NONE")

        candle_range = h - lo
        if candle_range == 0:
            return Signal("NONE")

        body = abs(c - o)
        body_pct = body / candle_range * 100

        met, failed = [], []

        if body_pct <= 10:
            met.append(f"Doji: body {body_pct:.1f}% of range (indecision)")
        else:
            failed.append(f"Not a Doji (body {body_pct:.1f}% of range, need ≤ 10%)")

        prev_c = float(r_prev["close"])
        prev_o = float(r_prev["open"])
        prev_was_red = prev_c < prev_o
        if prev_was_red:
            met.append(f"Doji after red candle (potential reversal)")
        else:
            failed.append("Prior candle was green (not a reversal setup)")

        if rsi < 50:
            met.append(f"RSI {rsi:.1f} < 50 (in bearish zone, due for bounce)")
        else:
            failed.append(f"RSI {rsi:.1f} ≥ 50")

        if c < sma20:
            met.append(f"Below SMA20 {sma20:.1f} (oversold territory)")
        else:
            failed.append(f"Close {c:.1f} above SMA20 {sma20:.1f}")

        if vol_ratio > 0.8:
            met.append(f"Volume {vol_ratio:.2f}x (decent participation)")
        else:
            failed.append(f"Very low volume {vol_ratio:.2f}x")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        shadow_ratio = (h - max(o, c)) / candle_range if candle_range > 0 else 0
        confidence = min(0.72, 0.50 + (10 - body_pct) / 50 + (len(met) - 3) * 0.04)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.55,
            expected_upside_pct=4.0,
            stop_loss_pct=3.0,
            target_pct=5.0,
            holding_days=3,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14", "sma_20", "volume_ratio"]
