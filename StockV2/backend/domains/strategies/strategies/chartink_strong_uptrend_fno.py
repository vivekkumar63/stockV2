import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkStrongUptrendFNO(BaseStrategy):
    """Chartink: Strong Uptrend F&O (Prabhu) — flexible OR-based trend + higher high/close."""
    name = "Chartink Strong Uptrend F&O"
    description = "(MACD>0 OR ADX>25 OR EMA5>SMA20>SMA50) + RSI 30-70 + higher close + higher high"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 15

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 52:
            return Signal("NONE")

        r = df.iloc[-1]
        r_prev = df.iloc[-2]

        c = float(r["close"])
        h = float(r["high"])
        prev_c = float(r_prev["close"])
        prev_h = float(r_prev["high"])

        macd = r["macd"]
        macd_sig = r["macd_signal"]
        adx = r["adx_14"]
        ema5 = r["ema_5"]
        sma20 = r["sma_20"]
        sma50 = r["sma_50"]
        rsi = r["rsi_14"]
        vol_ratio = r["volume_ratio"]

        if any(pd.isna(x) for x in [rsi, vol_ratio, sma20, sma50]):
            return Signal("NONE")

        met, failed = [], []

        # Core OR condition: at least one of MACD>0, ADX>25, EMA alignment
        trend_conditions = []
        if not pd.isna(macd) and not pd.isna(macd_sig) and macd > 0:
            trend_conditions.append(f"MACD {macd:.3f} > 0")
        if not pd.isna(adx) and adx > 25:
            trend_conditions.append(f"ADX {adx:.1f} > 25 (strong trend)")
        if not pd.isna(ema5) and ema5 > sma20 > sma50:
            trend_conditions.append(f"EMA5 {ema5:.1f} > SMA20 {sma20:.1f} > SMA50 {sma50:.1f}")

        if trend_conditions:
            met.append("Trend confirmed: " + " | ".join(trend_conditions))
        else:
            failed.append("No trend condition met (MACD≤0, ADX<25, EMA not aligned)")

        if 30 < rsi < 70:
            met.append(f"RSI {rsi:.1f} in healthy range (30-70)")
        else:
            failed.append(f"RSI {rsi:.1f} outside 30-70 range")

        if c > prev_c:
            met.append(f"Higher close: {prev_c:.1f} → {c:.1f} (+{(c/prev_c - 1)*100:.2f}%)")
        else:
            failed.append(f"Lower close: {c:.1f} < prev {prev_c:.1f}")

        if h > prev_h:
            met.append(f"Higher high: {prev_h:.1f} → {h:.1f} (+{(h/prev_h - 1)*100:.2f}%)")
        else:
            failed.append(f"Lower high: {h:.1f} ≤ prev {prev_h:.1f}")

        if vol_ratio > 1.0:
            met.append(f"Volume {vol_ratio:.2f}x above average")
        else:
            failed.append(f"Low volume {vol_ratio:.2f}x")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        trend_score = len(trend_conditions) / 3
        confidence = min(0.87, 0.55 + trend_score * 0.15 + (len(met) - 3) * 0.04)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.38,
            expected_upside_pct=10.0,
            stop_loss_pct=4.0,
            target_pct=10.0,
            holding_days=10,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["macd", "macd_signal", "adx_14", "ema_5", "sma_20", "sma_50", "rsi_14", "volume_ratio"]
