"""
Smart Money MFI + OBV Divergence

The dumbest money is retail. The smartest money is institutions.
They have to buy slowly — they can't dump $50M in one day without moving price.
So they accumulate over days/weeks. The fingerprint they leave:

1. MFI (Money Flow Index) falls below 25 — weighted by volume, so this means
   LARGE money stopped flowing in. Price falls.
2. OBV stays flat or rises while price falls — big players are quietly absorbing
   every share that panicking retail sells.
3. Price is still above SMA 50 — this is a quality company, not a disaster.
4. The last 3 bars of price are HIGHER than the MFI trough — price is stabilizing
   even though retail thinks it's still falling.

When you see OBV holding up while price and MFI look ugly, that's institutions
loading up. You want to be in the same trade as the institutions.
"""
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_LOOKBACK = 12


class SmartMoneyMFIOBVStrategy(BaseStrategy):
    name = "Smart Money MFI+OBV Divergence"
    description = "Buy institutional accumulation: MFI oversold but OBV stable/rising while price holds SMA50"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 5
    max_holding_days = 20
    weight = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["mfi_14", "obv", "obv_sma_10", "close", "sma_50", "rsi_14", "volume_ratio", "adx_14"]
        if len(df) < _LOOKBACK + 5 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        curr = df.iloc[-1]
        mfi = curr["mfi_14"]
        obv = curr["obv"]
        obv_sma = curr["obv_sma_10"]
        close = curr["close"]
        sma_50 = curr["sma_50"]
        rsi = curr["rsi_14"]
        volume_ratio = curr["volume_ratio"]
        adx = curr["adx_14"]

        if any(pd.isna(x) for x in [mfi, obv, obv_sma, close, sma_50, rsi, volume_ratio, adx]):
            return Signal(signal_type="NONE", conditions_failed=["Missing indicator values"])

        window = df.iloc[-_LOOKBACK:]

        # MFI low point in recent window
        mfi_min_recent = window["mfi_14"].min()
        mfi_min_idx = window["mfi_14"].idxmin()

        # OBV at the MFI trough vs OBV now
        obv_at_mfi_trough = window.loc[mfi_min_idx, "obv"] if mfi_min_idx in window.index else obv
        price_at_mfi_trough = window.loc[mfi_min_idx, "close"] if mfi_min_idx in window.index else close

        # Price trend over last 3 bars (stabilizing?)
        price_3bar_change = ((close - df["close"].iloc[-4]) / df["close"].iloc[-4]) * 100

        conditions_met = []
        conditions_failed = []

        # Condition 1: MFI was deeply oversold recently (money flow dried up)
        if mfi_min_recent < 25:
            conditions_met.append(
                f"MFI reached {mfi_min_recent:.1f} (deeply oversold) — selling exhaustion"
            )
        else:
            conditions_failed.append(f"MFI min={mfi_min_recent:.1f} not deeply oversold (<25)")

        # Condition 2: OBV did NOT fall with price — divergence = accumulation
        obv_held = obv >= obv_at_mfi_trough * 0.98  # OBV within 2% of trough level
        if obv_held and close < price_at_mfi_trough:
            conditions_met.append(
                f"OBV divergence: price fell from {price_at_mfi_trough:.2f} but OBV held (accumulation)"
            )
        else:
            conditions_failed.append("No OBV divergence vs MFI trough")

        # Condition 3: OBV above its 10-period SMA (overall accumulation trend)
        if obv > obv_sma:
            conditions_met.append("OBV above SMA10 (institutional accumulation trend)")
        else:
            conditions_failed.append("OBV below SMA10 (distribution)")

        # Condition 4: Price above SMA 50 (institutional support level)
        if close > sma_50:
            pct = ((close - sma_50) / sma_50) * 100
            conditions_met.append(f"Price {pct:.1f}% above SMA50 (institutional support intact)")
        else:
            conditions_failed.append("Price below SMA50 (support broken)")

        # Condition 5: Current MFI recovering from trough (not still falling)
        if mfi > mfi_min_recent + 3:
            conditions_met.append(
                f"MFI={mfi:.1f} recovering from trough {mfi_min_recent:.1f} (+{mfi - mfi_min_recent:.1f})"
            )
        else:
            conditions_failed.append(f"MFI={mfi:.1f} not yet recovering from trough {mfi_min_recent:.1f}")

        if len(conditions_met) == 5:
            mfi_depth = (25 - mfi_min_recent) / 25  # Deeper oversold = more explosive recovery
            obv_divergence_score = min(abs(obv - obv_at_mfi_trough) / abs(obv_at_mfi_trough + 1), 1.0)
            confidence = 0.67 + (0.12 * mfi_depth) + (0.08 * obv_divergence_score)
            return Signal(
                signal_type="BUY",
                confidence=round(min(confidence, 0.90), 4),
                risk_score=0.30,
                expected_upside_pct=11.0,
                stop_loss_pct=5.0,
                target_pct=11.0,
                holding_days=13,
                conditions_met=conditions_met,
            )

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed)

    def get_required_indicators(self) -> list[str]:
        return ["mfi_14", "obv", "obv_sma_10", "close", "sma_50", "rsi_14", "volume_ratio", "adx_14"]
