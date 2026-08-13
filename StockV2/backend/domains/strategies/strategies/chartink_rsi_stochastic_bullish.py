import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkRSIStochasticBullish(BaseStrategy):
    """Chartink: Bullish RSI-Stochastic — both RSI and Stochastic in bullish zones simultaneously."""
    name = "Chartink RSI + Stochastic Bullish"
    description = "RSI > 50 + Stoch K > D + Stoch K > 50 + MACD positive + uptrend (4/5 needed)"
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
        rsi = r["rsi_14"]
        stoch_k = r["stoch_k"]
        stoch_d = r["stoch_d"]
        prev_stoch_k = r_prev["stoch_k"]
        prev_stoch_d = r_prev["stoch_d"]
        macd = r["macd"]
        macd_sig = r["macd_signal"]
        sma20 = r["sma_20"]
        sma50 = r["sma_50"]
        vol_ratio = r["volume_ratio"]

        if any(pd.isna(x) for x in [rsi, stoch_k, stoch_d, macd, macd_sig, vol_ratio]):
            return Signal("NONE")

        met, failed = [], []

        if rsi > 50:
            met.append(f"RSI {rsi:.1f} > 50 (bullish)")
        else:
            failed.append(f"RSI {rsi:.1f} < 50")

        if stoch_k > stoch_d:
            met.append(f"Stoch K {stoch_k:.1f} > D {stoch_d:.1f} (K above D)")
        else:
            failed.append(f"Stoch K {stoch_k:.1f} < D {stoch_d:.1f}")

        if stoch_k > 50:
            met.append(f"Stoch K {stoch_k:.1f} > 50 (bullish zone)")
        else:
            failed.append(f"Stoch K {stoch_k:.1f} < 50 (bearish zone)")

        if not pd.isna(prev_stoch_k) and not pd.isna(prev_stoch_d):
            if prev_stoch_k <= prev_stoch_d and stoch_k > stoch_d:
                met.append(f"Stoch K just crossed above D (fresh crossover!)")

        if macd > macd_sig:
            met.append(f"MACD {macd:.3f} > signal {macd_sig:.3f} (bullish)")
        else:
            failed.append(f"MACD bearish ({macd:.3f} < {macd_sig:.3f})")

        if not pd.isna(sma20) and not pd.isna(sma50) and sma20 > sma50:
            met.append(f"Uptrend: SMA20 {sma20:.1f} > SMA50 {sma50:.1f}")
        elif not pd.isna(sma20) and not pd.isna(sma50):
            failed.append(f"Downtrend: SMA20 < SMA50")

        if vol_ratio > 1.0:
            met.append(f"Volume {vol_ratio:.2f}x above average")
        else:
            failed.append(f"Low volume {vol_ratio:.2f}x")

        if len(met) < 4:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        momentum = (rsi - 50) / 50 + (stoch_k - 50) / 100
        confidence = min(0.85, 0.55 + momentum * 0.10 + (len(met) - 4) * 0.04)

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
        return ["rsi_14", "stoch_k", "stoch_d", "macd", "macd_signal", "sma_20", "sma_50", "volume_ratio"]
