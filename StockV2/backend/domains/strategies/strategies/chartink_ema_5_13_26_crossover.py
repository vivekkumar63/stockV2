import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkEMA51326Crossover(BaseStrategy):
    """Chartink: EMA crossover(5,13,26) — fast EMA stack with crossover from 2 days ago."""
    name = "Chartink EMA 5-13-26 Crossover"
    description = "EMA5>EMA13>EMA26 aligned + fresh crossover within 2 days + volume + RSI"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 2
    max_holding_days = 10

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 35:
            return Signal("NONE")

        r = df.iloc[-1]
        r_prev = df.iloc[-2]
        r_prev2 = df.iloc[-3]

        ema5 = r["ema_5"]
        ema13 = r["ema_13"]
        ema26 = r["ema_26"]
        rsi = r["rsi_14"]
        vol_ratio = r["volume_ratio"]
        macd = r["macd"]
        macd_sig = r["macd_signal"]

        prev_ema5 = r_prev["ema_5"]
        prev_ema13 = r_prev["ema_13"]
        prev2_ema5 = r_prev2["ema_5"]
        prev2_ema13 = r_prev2["ema_13"]

        if any(pd.isna(x) for x in [ema5, ema13, ema26, rsi, vol_ratio]):
            return Signal("NONE")

        met, failed = [], []

        if ema5 > ema13 > ema26:
            spread = (ema5 - ema26) / ema26 * 100
            met.append(f"EMA5 {ema5:.1f} > EMA13 {ema13:.1f} > EMA26 {ema26:.1f} (spread +{spread:.2f}%)")
        else:
            failed.append(f"EMAs not aligned (5:{ema5:.1f}, 13:{ema13:.1f}, 26:{ema26:.1f})")

        # Check if EMA5 crossed above EMA13 in the last 2 days (the "2 days ago" condition)
        crossed_today = (not pd.isna(prev_ema5) and not pd.isna(prev_ema13)
                         and prev_ema5 <= prev_ema13 and ema5 > ema13)
        crossed_yesterday = (not pd.isna(prev2_ema5) and not pd.isna(prev2_ema13)
                             and prev2_ema5 <= prev2_ema13
                             and not pd.isna(prev_ema5) and not pd.isna(prev_ema13)
                             and prev_ema5 > prev_ema13)

        if crossed_today:
            met.append(f"EMA5 just crossed above EMA13 today (fresh signal!)")
        elif crossed_yesterday:
            met.append(f"EMA5 crossed above EMA13 yesterday (recent crossover)")
        elif ema5 > ema13:
            met.append(f"EMA5 above EMA13 (trend intact)")
        else:
            failed.append("EMA5 not above EMA13")

        if not pd.isna(macd) and not pd.isna(macd_sig) and macd > macd_sig:
            met.append(f"MACD {macd:.3f} > signal {macd_sig:.3f} (confirmed)")
        elif not pd.isna(macd) and not pd.isna(macd_sig):
            failed.append(f"MACD bearish ({macd:.3f} < {macd_sig:.3f})")

        if 45 < rsi < 75:
            met.append(f"RSI {rsi:.1f} in sweet spot (45-75)")
        else:
            failed.append(f"RSI {rsi:.1f} outside 45-75")

        if vol_ratio > 1.0:
            met.append(f"Volume {vol_ratio:.2f}x above average")
        else:
            failed.append(f"Low volume {vol_ratio:.2f}x")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        is_fresh = 1 if (crossed_today or crossed_yesterday) else 0
        ema_spread = (ema5 - ema26) / ema26 * 100 if ema26 > 0 else 0
        confidence = min(0.86, 0.55 + is_fresh * 0.08 + ema_spread / 20 + (len(met) - 3) * 0.04)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.40,
            expected_upside_pct=8.0,
            stop_loss_pct=3.5,
            target_pct=8.0,
            holding_days=7,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["ema_5", "ema_13", "ema_26", "rsi_14", "volume_ratio", "macd", "macd_signal"]
