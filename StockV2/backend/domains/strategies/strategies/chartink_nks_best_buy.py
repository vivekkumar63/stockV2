import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkNKSBestBuy(BaseStrategy):
    """Chartink: NKS Best Buy Intraday — multi-indicator confluence buy setup."""
    name = "Chartink NKS Best Buy Intraday"
    description = "EMA9>EMA21 + RSI>55 + MACD bullish + SuperTrend bullish + volume + green candle (5/6)"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 1
    max_holding_days = 5

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 35:
            return Signal("NONE")

        r = df.iloc[-1]
        c = float(r["close"])
        o = float(r["open"])
        ema9 = r["ema_9"]
        ema21 = r["ema_21"]
        rsi = r["rsi_14"]
        macd = r["macd"]
        macd_sig = r["macd_signal"]
        macd_hist = r["macd_hist"]
        st_dir = r["supertrend_direction"]
        vol_ratio = r["volume_ratio"]

        if any(pd.isna(x) for x in [ema9, ema21, rsi, macd, macd_sig, vol_ratio]):
            return Signal("NONE")

        met, failed = [], []

        if ema9 > ema21:
            met.append(f"EMA9 {ema9:.1f} > EMA21 {ema21:.1f} (short-term trend up)")
        else:
            failed.append(f"EMA9 {ema9:.1f} < EMA21 {ema21:.1f} (bearish)")

        if rsi > 55:
            met.append(f"RSI {rsi:.1f} > 55 (strong momentum)")
        else:
            failed.append(f"RSI {rsi:.1f} ≤ 55")

        if macd > macd_sig and (not pd.isna(macd_hist) and macd_hist > 0):
            met.append(f"MACD {macd:.3f} > signal, hist positive (bullish)")
        elif macd > macd_sig:
            met.append(f"MACD {macd:.3f} > signal {macd_sig:.3f}")
        else:
            failed.append(f"MACD bearish ({macd:.3f} < {macd_sig:.3f})")

        if not pd.isna(st_dir) and st_dir == 1.0:
            met.append("SuperTrend bullish (+1)")
        else:
            failed.append("SuperTrend not bullish")

        if vol_ratio > 1.0:
            met.append(f"Volume {vol_ratio:.2f}x above average")
        else:
            failed.append(f"Low volume {vol_ratio:.2f}x")

        if c > o:
            met.append(f"Green candle +{(c/o - 1)*100:.2f}%")
        else:
            failed.append("Red candle")

        if len(met) < 4:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        confidence = min(0.88, 0.55 + (rsi - 55) / 100 + len(met) * 0.04)

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
        return ["ema_9", "ema_21", "rsi_14", "macd", "macd_signal", "macd_hist",
                "supertrend_direction", "volume_ratio"]
