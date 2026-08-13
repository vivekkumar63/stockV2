import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkFNOBullishTrend(BaseStrategy):
    """Chartink: FNO Bullish Trend (Prabhu) — SMA + ADX + MACD triple confirmation trend filter."""
    name = "Chartink FNO Bullish MA+ADX+MACD"
    description = "SMA20>SMA50 + ADX>25 + MACD bullish + close>SMA20 + volume (4/5 needed)"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 5
    max_holding_days = 20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 52:
            return Signal("NONE")

        r = df.iloc[-1]
        c = float(r["close"])
        sma20 = r["sma_20"]
        sma50 = r["sma_50"]
        adx = r["adx_14"]
        macd = r["macd"]
        macd_sig = r["macd_signal"]
        macd_hist = r["macd_hist"]
        rsi = r["rsi_14"]
        vol_ratio = r["volume_ratio"]

        if any(pd.isna(x) for x in [sma20, sma50, adx, macd, macd_sig, rsi, vol_ratio]):
            return Signal("NONE")

        met, failed = [], []

        if sma20 > sma50:
            met.append(f"Uptrend: SMA20 {sma20:.1f} > SMA50 {sma50:.1f}")
        else:
            failed.append(f"Downtrend (SMA20 {sma20:.1f} < SMA50 {sma50:.1f})")

        if adx > 25:
            met.append(f"ADX {adx:.1f} > 25 (strong trend)")
        else:
            failed.append(f"ADX {adx:.1f} weak (< 25)")

        if macd > macd_sig and macd_hist > 0:
            met.append(f"MACD {macd:.3f} > signal {macd_sig:.3f}, hist positive")
        else:
            failed.append(f"MACD not bullish ({macd:.3f} vs signal {macd_sig:.3f})")

        if c > sma20:
            met.append(f"Close {c:.1f} above SMA20 {sma20:.1f}")
        else:
            failed.append(f"Close {c:.1f} below SMA20 {sma20:.1f}")

        if vol_ratio > 1.0:
            met.append(f"Volume {vol_ratio:.2f}x above average")
        else:
            failed.append(f"Below-average volume ({vol_ratio:.2f}x)")

        if rsi > 50:
            met.append(f"RSI {rsi:.1f} > 50 (bullish momentum)")
        else:
            failed.append(f"RSI {rsi:.1f} < 50")

        if len(met) < 4:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        trend_strength = (adx - 25) / 50
        confidence = min(0.88, 0.58 + trend_strength * 0.15 + (len(met) - 4) * 0.04)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.35,
            expected_upside_pct=12.0,
            stop_loss_pct=5.0,
            target_pct=12.0,
            holding_days=12,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["sma_20", "sma_50", "adx_14", "macd", "macd_signal", "macd_hist", "rsi_14", "volume_ratio"]
