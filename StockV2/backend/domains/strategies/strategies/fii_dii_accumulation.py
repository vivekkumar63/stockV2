import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_VOL_MULTIPLIER  = 1.5   # volume must exceed vol_sma by this factor
_MIN_HIGH_VOL    = 3     # minimum bars with high volume in last 5
_MIN_ABOVE_SMA   = 3     # minimum bars above SMA50 in last 5
_RSI_MIN         = 40.0  # RSI lower bound (not oversold)
_RSI_MAX         = 70.0  # RSI upper bound (not overbought)
_BUY_CONFIDENCE  = 0.65  # fixed confidence when all 3 conditions met


class FIIDIIAccumulationStrategy(BaseStrategy):
    name = "FII/DII Accumulation"
    description = (
        "Detects institutional accumulation via price/volume proxies: "
        "volume > 1.5× average for 3 of last 5 days, close > SMA50 for 3 of last 5 days, RSI 40-70."
    )
    strategy_type = StrategyType.FUNDAMENTAL
    timeframe = Timeframe.DAILY
    min_holding_days = 10
    max_holding_days = 30
    weight = 0.05

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if df.empty or len(df) < 10:
            return Signal("NONE")

        required = ["volume_sma_20", "sma_50", "rsi_14"]
        if not all(c in df.columns for c in required):
            return Signal("NONE")

        last5 = df.tail(5)
        last  = df.iloc[-1]
        rsi   = float(last["rsi_14"])

        if pd.isna(rsi):
            return Signal("NONE")

        # Condition 1: volume > 1.5× vol_sma for ≥3 of last 5 bars
        vol_high = (last5["volume"] > last5["volume_sma_20"] * _VOL_MULTIPLIER).sum()

        # Condition 2: close > sma_50 for ≥3 of last 5 bars
        above_sma = (last5["close"] > last5["sma_50"]).sum()

        # Condition 3: RSI in accumulation range
        rsi_ok = _RSI_MIN <= rsi <= _RSI_MAX

        met    = []
        missed = []

        if vol_high >= _MIN_HIGH_VOL:
            met.append(f"High volume {vol_high}/5 bars (accumulation)")
        else:
            missed.append(f"Only {vol_high}/5 bars with high volume (need ≥{_MIN_HIGH_VOL})")

        if above_sma >= _MIN_ABOVE_SMA:
            met.append(f"Above SMA50 {above_sma}/5 bars (uptrend)")
        else:
            missed.append(f"Only {above_sma}/5 bars above SMA50 (need ≥{_MIN_ABOVE_SMA})")

        if rsi_ok:
            met.append(f"RSI {rsi:.1f} in {_RSI_MIN:.0f}–{_RSI_MAX:.0f} (not overbought)")
        else:
            missed.append(f"RSI {rsi:.1f} outside {_RSI_MIN:.0f}–{_RSI_MAX:.0f}")

        if len(met) == 3:
            return Signal(
                signal_type="BUY",
                confidence=_BUY_CONFIDENCE,
                risk_score=0.40,
                expected_upside_pct=15.0,
                stop_loss_pct=7.0,
                target_pct=15.0,
                holding_days=20,
                conditions_met=met,
                conditions_failed=missed,
            )
        return Signal("NONE", conditions_met=met, conditions_failed=missed)

    def get_required_indicators(self) -> list[str]:
        return ["volume_sma_20", "sma_50", "rsi_14"]
