import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class Chartink52WeekHighBreakout(BaseStrategy):
    """Chartink: 52-Week High Breakout — price breaking out to new highs with volume confirmation."""
    name = "Chartink 52-Week High Breakout"
    description = "Close within 1% of 52-week high + volume surge + MACD bullish + RSI 55-80"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 5
    max_holding_days = 20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 50:
            return Signal("NONE")

        r = df.iloc[-1]
        c = float(r["close"])
        macd = r["macd"]
        macd_sig = r["macd_signal"]
        rsi = r["rsi_14"]
        vol_ratio = r["volume_ratio"]
        sma20 = r["sma_20"]

        if any(pd.isna(x) for x in [macd, macd_sig, rsi, vol_ratio, sma20]):
            return Signal("NONE")

        high_52w = float(df["high"].max())
        prev_high_52w = float(df["high"].iloc[:-1].max())

        met, failed = [], []

        pct_from_high = (high_52w - c) / high_52w * 100
        if pct_from_high <= 1.0:
            met.append(f"Within {pct_from_high:.2f}% of 52-week high {high_52w:.2f}")
        else:
            failed.append(f"{pct_from_high:.1f}% below 52-week high {high_52w:.2f}")

        if c >= prev_high_52w:
            met.append(f"Breaking to new 52-week high (prev: {prev_high_52w:.2f})")
        else:
            failed.append(f"Not breaking previous high {prev_high_52w:.2f}")

        if vol_ratio > 1.5:
            met.append(f"Volume {vol_ratio:.2f}x (strong breakout volume)")
        elif vol_ratio > 1.0:
            met.append(f"Volume {vol_ratio:.2f}x above average")
        else:
            failed.append(f"Breakout on low volume ({vol_ratio:.2f}x)")

        if macd > macd_sig:
            met.append(f"MACD {macd:.3f} > signal {macd_sig:.3f} (bullish)")
        else:
            failed.append(f"MACD bearish ({macd:.3f} < {macd_sig:.3f})")

        if 55 < rsi < 80:
            met.append(f"RSI {rsi:.1f} in momentum zone (55-80)")
        else:
            failed.append(f"RSI {rsi:.1f} outside 55-80 range")

        if c > sma20:
            met.append(f"Close {c:.1f} above SMA20 {sma20:.1f}")
        else:
            failed.append(f"Close {c:.1f} below SMA20 {sma20:.1f}")

        if len(met) < 4:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        is_new_high = 1 if c >= prev_high_52w else 0
        confidence = min(0.90, 0.60 + (1 - pct_from_high / 5) * 0.15 + is_new_high * 0.10 + (len(met) - 4) * 0.03)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.40,
            expected_upside_pct=15.0,
            stop_loss_pct=5.0,
            target_pct=15.0,
            holding_days=15,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["macd", "macd_signal", "rsi_14", "volume_ratio", "sma_20"]
