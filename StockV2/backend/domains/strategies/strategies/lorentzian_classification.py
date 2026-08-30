"""
Lorentzian Classification (KNN with Lorentzian Distance)

KNN (k=8) over 5 features: RSI(14), WaveTrend(10,11), CCI(20), ADX(14), RSI(9).
Distance metric: sum(log(1 + |current[k] - history[i][k]|)) — log-compresses outliers.
Label at bar i: 4-bar forward direction (+1 up, -1 down).
Prediction = sum of 8 nearest neighbors' labels.

BUY = prediction > 0 AND volatility expanding AND regime not collapsing.
"""
import numpy as np
import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_N_NEIGHBORS   = 8
_REGIME_THRESH = -0.1


def _volatility_filter(df: pd.DataFrame) -> bool:
    if len(df) < 12:
        return True
    h = df["high"].values; l = df["low"].values; c = df["close"].values
    tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])])
    return float(tr[-1]) > float(tr[-10:].mean())


def _regime_filter(close: pd.Series) -> bool:
    if len(close) < 12:
        return True
    slope = (float(close.iloc[-1]) - float(close.iloc[-11])) / float(close.iloc[-11])
    return slope >= _REGIME_THRESH


class LorentzianClassificationStrategy(BaseStrategy):
    name = "Lorentzian Classification"
    description = (
        "KNN (k=8) with Lorentzian distance over 5 features: RSI(14), "
        "WaveTrend(10,11), CCI(20), ADX(14), RSI(9). Votes on 4-bar forward "
        "direction. Filters: volatility expansion + regime (non-downtrend)."
    )
    strategy_type = StrategyType.TECHNICAL
    timeframe     = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 8
    weight           = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["close", "high", "low", "rsi_14", "cci_20", "adx_14", "lorentzian_pred"]
        if len(df) < 60 or not all(c in df.columns for c in required):
            return Signal(signal_type="NONE", conditions_failed=["Insufficient data"])

        pred = float(df["lorentzian_pred"].iloc[-1])
        if pd.isna(pred):
            return Signal(signal_type="NONE", conditions_failed=["Prediction not ready"])

        prediction = int(pred)
        vol_ok     = _volatility_filter(df)
        regime_ok  = _regime_filter(df["close"])

        conditions_met    = []
        conditions_failed = []

        vote_str = f"KNN prediction={prediction:+d}/{_N_NEIGHBORS} neighbors"
        if prediction > 0:
            conditions_met.append(vote_str)
        else:
            conditions_failed.append(vote_str)

        if vol_ok:
            conditions_met.append("Volatility expanding (ATR1 > ATR10)")
        else:
            conditions_failed.append("Volatility contracting (ATR1 ≤ ATR10)")

        if regime_ok:
            conditions_met.append("Regime: trend/flat (slope ≥ -0.1)")
        else:
            conditions_failed.append("Regime: downtrend filtered out")

        if prediction > 0 and vol_ok and regime_ok:
            conviction = abs(prediction) / _N_NEIGHBORS
            confidence = round(min(0.55 + 0.35 * conviction, 0.92), 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.35,
                expected_upside_pct=8.0,
                stop_loss_pct=5.0,
                target_pct=8.0,
                holding_days=6,
                conditions_met=conditions_met + [
                    f"RSI14={float(df['rsi_14'].iloc[-1]):.1f} "
                    f"CCI={float(df['cci_20'].iloc[-1]):.1f} "
                    f"ADX={float(df['adx_14'].iloc[-1]):.1f}",
                ],
            )

        return Signal(signal_type="NONE", conditions_met=conditions_met, conditions_failed=conditions_failed)

    def get_required_indicators(self) -> list[str]:
        return ["close", "high", "low", "rsi_14", "cci_20", "adx_14", "lorentzian_pred"]
