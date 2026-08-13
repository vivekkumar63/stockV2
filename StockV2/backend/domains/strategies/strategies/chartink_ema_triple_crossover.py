import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkEMATripleCrossover(BaseStrategy):
    """Chartink: EMA Triple Crossover — EMA5>EMA10>EMA21 alignment with MACD confirmation."""
    name = "Chartink EMA 5-10-21 Crossover"
    description = "EMA5 > EMA10 > EMA21 + MACD bullish + volume surge + RSI in sweet spot"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 12

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 35:
            return Signal("NONE")

        r = df.iloc[-1]
        r_prev = df.iloc[-2]

        c = float(r["close"])
        ema5 = r["ema_5"]
        ema10 = r["ema_10"]
        ema21 = r["ema_21"]
        macd = r["macd"]
        macd_sig = r["macd_signal"]
        rsi = r["rsi_14"]
        vol_ratio = r["volume_ratio"]

        prev_ema5 = r_prev["ema_5"]
        prev_ema10 = r_prev["ema_10"]

        if any(pd.isna(x) for x in [ema5, ema10, ema21, macd, macd_sig, rsi, vol_ratio]):
            return Signal("NONE")

        met, failed = [], []

        if ema5 > ema10 > ema21:
            met.append(f"EMA5 {ema5:.1f} > EMA10 {ema10:.1f} > EMA21 {ema21:.1f} (aligned)")
        else:
            failed.append(f"EMAs not in bullish order (5:{ema5:.1f}, 10:{ema10:.1f}, 21:{ema21:.1f})")

        if not pd.isna(prev_ema5) and not pd.isna(prev_ema10):
            if prev_ema5 <= prev_ema10 and ema5 > ema10:
                met.append(f"EMA5 just crossed above EMA10 (fresh signal)")
            elif ema5 > ema10:
                met.append(f"EMA5 {ema5:.1f} above EMA10 {ema10:.1f} (trend intact)")
            else:
                failed.append("EMA5 below EMA10")

        if macd > macd_sig:
            met.append(f"MACD {macd:.3f} > signal {macd_sig:.3f} (bullish)")
        else:
            failed.append(f"MACD bearish ({macd:.3f} < {macd_sig:.3f})")

        if 45 < rsi < 75:
            met.append(f"RSI {rsi:.1f} in momentum zone (45-75)")
        else:
            failed.append(f"RSI {rsi:.1f} outside 45-75 range")

        if vol_ratio > 1.0:
            met.append(f"Volume {vol_ratio:.2f}x above average")
        else:
            failed.append(f"Low volume {vol_ratio:.2f}x")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        spread_pct = (ema5 - ema21) / ema21 * 100
        confidence = min(0.85, 0.55 + spread_pct / 15 + (len(met) - 3) * 0.04)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.40,
            expected_upside_pct=8.0,
            stop_loss_pct=4.0,
            target_pct=8.0,
            holding_days=7,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["ema_5", "ema_10", "ema_21", "macd", "macd_signal", "rsi_14", "volume_ratio"]
