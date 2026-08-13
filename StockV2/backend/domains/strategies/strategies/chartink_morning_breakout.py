import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkMorningBreakout(BaseStrategy):
    """Chartink: Morning Breakout Scanner — gap-up open breaking yesterday's high with volume."""
    name = "Chartink Morning Breakout 9:30"
    description = "Gap-up open + close > PDH (yesterday's high) + volume surge + RSI > 55 + MACD"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 1
    max_holding_days = 4

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 22:
            return Signal("NONE")

        r = df.iloc[-1]
        r_prev = df.iloc[-2]

        c = float(r["close"])
        o = float(r["open"])
        prev_close = float(r_prev["close"])
        prev_high = float(r_prev["high"])
        rsi = r["rsi_14"]
        vol_ratio = r["volume_ratio"]
        macd = r["macd"]
        macd_sig = r["macd_signal"]
        gap_pct = r["gap_pct"]

        if any(pd.isna(x) for x in [rsi, vol_ratio]):
            return Signal("NONE")

        met, failed = [], []

        if not pd.isna(gap_pct) and gap_pct > 0.3:
            met.append(f"Gap-up open +{gap_pct:.2f}% above prev close {prev_close:.1f}")
        else:
            gap_val = gap_pct if not pd.isna(gap_pct) else 0
            failed.append(f"No gap-up (gap {gap_val:.2f}%)")

        if c > prev_high:
            breakout_pct = (c - prev_high) / prev_high * 100
            met.append(f"Close {c:.1f} broke PDH {prev_high:.1f} (+{breakout_pct:.2f}%)")
        else:
            failed.append(f"Close {c:.1f} failed to clear PDH {prev_high:.1f}")

        if c > o:
            met.append(f"Green candle +{(c/o - 1)*100:.2f}% (buyers in control)")
        else:
            failed.append("Red candle (selling after gap)")

        if vol_ratio > 1.5:
            met.append(f"Strong volume {vol_ratio:.2f}x (breakout confirmed)")
        elif vol_ratio > 1.0:
            met.append(f"Above-average volume {vol_ratio:.2f}x")
        else:
            failed.append(f"Weak volume {vol_ratio:.2f}x on breakout")

        if not pd.isna(rsi) and rsi > 55:
            met.append(f"RSI {rsi:.1f} > 55 (momentum)")
        elif not pd.isna(rsi):
            failed.append(f"RSI {rsi:.1f} ≤ 55")

        if not pd.isna(macd) and not pd.isna(macd_sig) and macd > macd_sig:
            met.append(f"MACD {macd:.3f} > signal (bullish)")
        elif not pd.isna(macd) and not pd.isna(macd_sig):
            failed.append(f"MACD bearish")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        breakout_pct = (c - prev_high) / prev_high * 100 if c > prev_high else 0
        gap_val = gap_pct if not pd.isna(gap_pct) else 0
        confidence = min(0.88, 0.55 + gap_val / 20 + breakout_pct / 15 + (len(met) - 3) * 0.04)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.45,
            expected_upside_pct=5.0,
            stop_loss_pct=2.0,
            target_pct=5.0,
            holding_days=2,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14", "volume_ratio", "macd", "macd_signal", "gap_pct"]
