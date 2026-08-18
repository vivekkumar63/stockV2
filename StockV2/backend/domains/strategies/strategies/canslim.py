import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_ROE_MIN        = 0.15   # A: minimum ROE (decimal)
_PE_MAX         = 30.0   # L: maximum P/E ratio
_HIGH_LOOKBACK  = 200    # N: rolling window bars
_HIGH_MIN_PRDS  = 100    # N: min_periods for rolling window
_NEAR_HIGH_PCT  = 0.85   # N: price must be >= 85% of rolling high
_BUY_THRESHOLD  = 5      # minimum criteria met to issue BUY
_TOTAL_CRITERIA = 6      # total criteria evaluated


class CANSLIMStrategy(BaseStrategy):
    name = "CANSLIM"
    description = (
        "William O'Neil's CANSLIM: quality growth companies near 52-week highs. "
        "Proxies: EPS>0 (C), ROE>15% (A), near 200-day high (N), volume spike (S), PE<30 (L), price>SMA50 (M)."
    )
    strategy_type = StrategyType.FUNDAMENTAL
    timeframe = Timeframe.DAILY
    min_holding_days = 20
    max_holding_days = 60
    weight = 0.05

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if not fundamentals:
            return Signal("NONE")

        eps = fundamentals.get("eps")
        roe = fundamentals.get("roe")
        pe  = fundamentals.get("pe_ratio")

        if df.empty or len(df) < 50:
            return Signal("NONE")

        last  = df.iloc[-1]
        close = float(last["close"])

        high_200 = df["high"].rolling(_HIGH_LOOKBACK, min_periods=_HIGH_MIN_PRDS).max().iloc[-1]
        sma_50   = float(last.get("sma_50", float("nan")))
        vol      = float(last["volume"])
        vol_sma  = float(last.get("volume_sma_20", float("nan")))

        met = []
        missed = []

        # C: Current EPS > 0 (profitable)
        if eps is not None and eps > 0:
            met.append(f"C: EPS={eps:.1f} > 0")
        else:
            missed.append("C: EPS not positive")

        # A: ROE > 15% (quality earnings)
        if roe is not None and roe > _ROE_MIN:
            met.append(f"A: ROE={roe*100:.1f}% > 15%")
        else:
            missed.append("A: ROE <= 15%")

        # N: Price within 15% of 200-day high
        if not pd.isna(high_200) and close >= high_200 * _NEAR_HIGH_PCT:
            met.append(f"N: close {close:.1f} within 15% of 200-day high {high_200:.1f}")
        else:
            missed.append("N: price not near 200-day high")

        # S: Volume above 20-day average (accumulation)
        if not pd.isna(vol_sma) and vol > vol_sma:
            met.append(f"S: volume {vol:.0f} > vol_sma_20 {vol_sma:.0f}")
        else:
            missed.append("S: volume not above average")

        # L: PE < 30 (not wildly overvalued)
        if pe is not None and pe < _PE_MAX:
            met.append(f"L: PE={pe:.1f} < 30")
        else:
            missed.append("L: PE >= 30 or unknown")

        # M: Price above SMA50 (uptrend)
        if not pd.isna(sma_50) and close > sma_50:
            met.append(f"M: close {close:.1f} > SMA50 {sma_50:.1f}")
        else:
            missed.append("M: price below SMA50")

        if len(met) >= _BUY_THRESHOLD:
            confidence = round(len(met) / _TOTAL_CRITERIA, 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.35,
                expected_upside_pct=20.0,
                stop_loss_pct=8.0,
                target_pct=20.0,
                holding_days=30,
                conditions_met=met,
                conditions_failed=missed,
            )
        return Signal("NONE", conditions_met=met, conditions_failed=missed)

    def get_required_indicators(self) -> list[str]:
        return ["sma_50", "volume_sma_20"]
