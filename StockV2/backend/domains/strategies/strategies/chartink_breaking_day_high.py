import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkBreakingDayHigh(BaseStrategy):
    """Chartink: Breaking Day's High — close decisively above previous day's high with strong volume."""
    name = "Chartink Breaking Day High"
    description = "Close > PDH by 0.5%+ + strong volume surge + RSI momentum + uptrend filter"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 1
    max_holding_days = 5

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 22:
            return Signal("NONE")

        r = df.iloc[-1]
        r_prev = df.iloc[-2]

        c = float(r["close"])
        o = float(r["open"])
        prev_high = float(r_prev["high"])
        prev_close = float(r_prev["close"])
        rsi = r["rsi_14"]
        vol_ratio = r["volume_ratio"]
        sma20 = r["sma_20"]
        adx = r["adx_14"]

        if any(pd.isna(x) for x in [rsi, vol_ratio]):
            return Signal("NONE")

        met, failed = [], []

        breakout_pct = (c - prev_high) / prev_high * 100
        if breakout_pct >= 0.5:
            met.append(f"Decisively broke PDH {prev_high:.1f} → close {c:.1f} (+{breakout_pct:.2f}%)")
        elif breakout_pct > 0:
            met.append(f"Closed above PDH {prev_high:.1f} (+{breakout_pct:.2f}%)")
        else:
            failed.append(f"Failed to clear PDH {prev_high:.1f} (close {c:.1f})")

        if vol_ratio > 1.5:
            met.append(f"Strong breakout volume {vol_ratio:.2f}x average")
        elif vol_ratio > 1.0:
            met.append(f"Above-average volume {vol_ratio:.2f}x")
        else:
            failed.append(f"Low volume {vol_ratio:.2f}x — weak breakout signal")

        if rsi > 55:
            met.append(f"RSI {rsi:.1f} > 55 (strong momentum)")
        elif rsi > 50:
            met.append(f"RSI {rsi:.1f} > 50 (bullish zone)")
        else:
            failed.append(f"RSI {rsi:.1f} < 50 (weak)")

        if c > o:
            met.append(f"Green candle +{(c/o - 1)*100:.2f}% (closed near highs)")
        else:
            failed.append("Closed red (sold into breakout)")

        if not pd.isna(sma20) and c > sma20:
            met.append(f"Above SMA20 {sma20:.1f} (trend support)")
        elif not pd.isna(sma20):
            failed.append(f"Below SMA20 {sma20:.1f}")

        if not pd.isna(adx) and adx > 20:
            met.append(f"ADX {adx:.1f} > 20 (trending)")
        elif not pd.isna(adx):
            failed.append(f"ADX {adx:.1f} < 20 (choppy)")

        if len(met) < 3:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        confidence = min(0.88, 0.55 + breakout_pct / 10 + (len(met) - 3) * 0.05)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.40,
            expected_upside_pct=5.0,
            stop_loss_pct=2.5,
            target_pct=5.0,
            holding_days=3,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14", "volume_ratio", "sma_20", "adx_14"]
