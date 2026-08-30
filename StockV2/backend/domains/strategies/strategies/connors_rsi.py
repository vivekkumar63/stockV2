"""
Connors RSI (CRSI) — Larry Connors & Cesar Alvarez (2012)

CRSI = (RSI(3) + StreakRSI(2) + PercentRank(100)) / 3

BUY = CRSI < 20 (composite oversold)
      AND price above SMA(200) — quality uptrending stocks only
      AND close > close[-5]  (beginning to stabilize, not in free-fall)
"""
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_CRSI_OVERSOLD = 20
_CRSI_EXTREME  = 10


class ConnorsRSIStrategy(BaseStrategy):
    name = "Connors RSI"
    description = (
        "CRSI = (RSI3 + StreakRSI2 + PercentRank100) / 3. "
        "BUY when composite oversold (<20) in stocks above SMA200."
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe     = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 10
    weight           = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["close", "connors_rsi", "sma_200"]
        if len(df) < 110 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data (need 110+ bars)"])

        crsi    = float(df["connors_rsi"].iloc[-1])
        sma_200 = float(df["sma_200"].iloc[-1])
        c_now   = float(df["close"].iloc[-1])
        c_5ago  = float(df["close"].iloc[-6])

        if pd.isna(crsi):
            return Signal(signal_type="NONE", conditions_failed=["CRSI not ready"])

        above_200   = pd.isna(sma_200) or (c_now > sma_200)
        stabilizing = c_now > c_5ago

        conditions_met    = []
        conditions_failed = []

        if crsi < _CRSI_EXTREME:
            conditions_met.append(f"CRSI={crsi:.1f} EXTREME oversold (<{_CRSI_EXTREME})")
        elif crsi < _CRSI_OVERSOLD:
            conditions_met.append(f"CRSI={crsi:.1f} oversold (<{_CRSI_OVERSOLD})")
        else:
            conditions_failed.append(f"CRSI={crsi:.1f} not oversold (need <{_CRSI_OVERSOLD})")

        if above_200:
            if not pd.isna(sma_200):
                pct = ((c_now - sma_200) / sma_200) * 100
                conditions_met.append(f"Price {pct:.1f}% above SMA(200) — quality uptrend")
            else:
                conditions_met.append("SMA(200) not computed — filter skipped")
        else:
            conditions_failed.append(f"Price below SMA(200) ({sma_200:.2f}) — avoid bottom-fishing")

        if stabilizing:
            pct = ((c_now - c_5ago) / c_5ago) * 100
            conditions_met.append(f"Price stabilizing: {pct:+.1f}% vs 5 days ago")
        else:
            conditions_failed.append("Price still falling vs 5 days ago — not yet stabilizing")

        if crsi < _CRSI_OVERSOLD and above_200 and stabilizing:
            extreme_bonus = 0.10 if crsi < _CRSI_EXTREME else 0.0
            depth      = max(0, _CRSI_OVERSOLD - crsi) / _CRSI_OVERSOLD
            confidence = round(min(0.62 + 0.18 * depth + extreme_bonus, 0.88), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.25,
                expected_upside_pct=7.0,
                stop_loss_pct=4.0,
                target_pct=7.0,
                holding_days=5,
                conditions_met=conditions_met,
            )

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed)

    def get_required_indicators(self) -> list[str]:
        return ["close", "connors_rsi", "sma_200"]
