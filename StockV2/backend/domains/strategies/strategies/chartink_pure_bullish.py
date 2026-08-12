import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkPureBullish(BaseStrategy):
    """Chartink: Pure Bullish Trend — 8+ of 11 technical indicators aligned bullishly."""
    name = "Pure Bullish Confluence"
    description = "MACD+RSI+CCI+MFI+Williams+Stoch+SMA+ADX+BB+Volume+Green candle — needs 8/11"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 5
    max_holding_days = 20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 52:
            return Signal("NONE")

        r = df.iloc[-1]
        c = float(r["close"])
        o = float(r["open"])

        checks: list[tuple[bool, str]] = []

        def safe(val) -> bool:
            return not pd.isna(val)

        if safe(r["macd"]) and safe(r["macd_signal"]):
            checks.append((r["macd"] > r["macd_signal"] and r["macd_hist"] > 0,
                           f"MACD {r['macd']:.3f} > signal {r['macd_signal']:.3f}"))

        if safe(r["rsi_14"]):
            checks.append((50 < r["rsi_14"] < 75,
                           f"RSI {r['rsi_14']:.1f} in 50-75 range"))

        if safe(r["cci_20"]):
            checks.append((r["cci_20"] > 0,
                           f"CCI {r['cci_20']:.1f} > 0"))

        if safe(r["mfi_14"]):
            checks.append((r["mfi_14"] > 40,
                           f"MFI {r['mfi_14']:.1f} > 40"))

        if safe(r["williams_r"]):
            checks.append((r["williams_r"] > -50,
                           f"Williams %R {r['williams_r']:.1f} > -50"))

        if safe(r["stoch_k"]) and safe(r["stoch_d"]):
            checks.append((r["stoch_k"] > r["stoch_d"],
                           f"Stoch K {r['stoch_k']:.1f} > D {r['stoch_d']:.1f}"))

        if safe(r["sma_20"]) and safe(r["sma_50"]):
            checks.append((c > r["sma_20"] and c > r["sma_50"],
                           f"Close above SMA20 ({r['sma_20']:.1f}) & SMA50 ({r['sma_50']:.1f})"))

        if safe(r["adx_14"]):
            checks.append((r["adx_14"] > 20,
                           f"ADX {r['adx_14']:.1f} > 20 (trending)"))

        if safe(r["bb_upper"]):
            checks.append((c >= r["bb_upper"],
                           f"Close {c:.1f} at/above BB upper {r['bb_upper']:.1f}"))

        if safe(r["volume_ratio"]):
            checks.append((r["volume_ratio"] > 1.0,
                           f"Volume ratio {r['volume_ratio']:.2f}x"))

        checks.append((c > o, f"Green candle (close {c:.1f} > open {o:.1f})"))

        met = [desc for passed, desc in checks if passed]
        failed = [desc for passed, desc in checks if not passed]

        if len(met) < 8:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        confidence = min(0.95, 0.55 + len(met) * 0.04)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.30,
            expected_upside_pct=15.0,
            stop_loss_pct=5.0,
            target_pct=15.0,
            holding_days=15,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["macd", "macd_signal", "macd_hist", "rsi_14", "cci_20",
                "mfi_14", "williams_r", "stoch_k", "stoch_d", "sma_20",
                "sma_50", "adx_14", "bb_upper", "volume_ratio"]
