import pandas as pd
import ta


class IndicatorEngine:
    """Computes all technical indicators on an OHLCV DataFrame.

    Input columns required: open, high, low, close, volume (lowercase).
    Returns a new DataFrame with all indicator columns appended.
    Does not modify the input DataFrame.
    """

    @staticmethod
    def compute(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df.copy()

        out = df.copy()
        close = out["close"]
        high = out["high"]
        low = out["low"]
        volume = out["volume"].astype(float)
        n = len(df)

        # ── Moving Averages ──────────────────────────────────────────
        out["sma_20"] = ta.trend.SMAIndicator(close, window=20).sma_indicator() if n >= 20 else pd.Series(float("nan"), index=close.index)
        out["sma_50"] = ta.trend.SMAIndicator(close, window=50).sma_indicator() if n >= 50 else pd.Series(float("nan"), index=close.index)
        out["ema_9"] = ta.trend.EMAIndicator(close, window=9).ema_indicator() if n >= 9 else pd.Series(float("nan"), index=close.index)
        out["ema_21"] = ta.trend.EMAIndicator(close, window=21).ema_indicator() if n >= 21 else pd.Series(float("nan"), index=close.index)

        # ── RSI ──────────────────────────────────────────────────────
        out["rsi_14"] = ta.momentum.RSIIndicator(close, window=14).rsi() if n >= 15 else pd.Series(float("nan"), index=close.index)

        # ── MACD (12, 26, 9) ────────────────────────────────────────
        if n >= 34:
            macd_ind = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
            out["macd"] = macd_ind.macd()
            out["macd_signal"] = macd_ind.macd_signal()
            out["macd_hist"] = macd_ind.macd_diff()
        else:
            out["macd"] = out["macd_signal"] = out["macd_hist"] = pd.Series(float("nan"), index=close.index)

        # ── Bollinger Bands (20, 2) ──────────────────────────────────
        if n >= 20:
            bb_ind = ta.volatility.BollingerBands(close, window=20, window_dev=2)
            out["bb_upper"] = bb_ind.bollinger_hband()
            out["bb_middle"] = bb_ind.bollinger_mavg()
            out["bb_lower"] = bb_ind.bollinger_lband()
        else:
            out["bb_upper"] = out["bb_middle"] = out["bb_lower"] = pd.Series(float("nan"), index=close.index)

        # ── ATR — Wilder's smoothing via EWM to avoid ta library edge cases ──
        out["atr_14"] = IndicatorEngine._atr(high, low, close, window=14) if n >= 14 else pd.Series(float("nan"), index=close.index)

        # ── Volume ───────────────────────────────────────────────────
        out["volume_sma_20"] = ta.trend.SMAIndicator(volume, window=20).sma_indicator() if n >= 20 else pd.Series(float("nan"), index=close.index)
        out["volume_ratio"] = volume / out["volume_sma_20"].replace(0, float("nan"))

        # ── ADX ──────────────────────────────────────────────────────
        out["adx_14"] = ta.trend.ADXIndicator(high, low, close, window=14).adx() if n >= 28 else pd.Series(float("nan"), index=close.index)

        # ── Rate of Change ───────────────────────────────────────────
        out["roc_10"] = ta.momentum.ROCIndicator(close, window=10).roc() if n >= 11 else pd.Series(float("nan"), index=close.index)

        # ── SuperTrend (7, 3.0) ──────────────────────────────────────
        if n >= 14:
            out["supertrend"], out["supertrend_direction"] = IndicatorEngine._supertrend(
                high, low, close, period=7, multiplier=3.0
            )
        else:
            out["supertrend"] = out["supertrend_direction"] = pd.Series(float("nan"), index=close.index)

        return out

    @staticmethod
    def _atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
        """ATR using Wilder's EWM smoothing — avoids ta library's initialization edge case."""
        prev_close = close.shift(1)
        true_range = pd.concat([
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        return true_range.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()

    @staticmethod
    def _supertrend(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 7,
        multiplier: float = 3.0,
    ) -> tuple[pd.Series, pd.Series]:
        """SuperTrend indicator. Returns (supertrend_line, direction) where direction=1 is bullish."""
        atr = IndicatorEngine._atr(high, low, close, window=period)
        hl2 = (high + low) / 2

        raw_upper = hl2 + multiplier * atr
        raw_lower = hl2 - multiplier * atr

        supertrend = pd.Series(float("nan"), index=close.index)
        direction = pd.Series(float("nan"), index=close.index)

        final_upper = raw_upper.copy()
        final_lower = raw_lower.copy()

        for i in range(1, len(close)):
            if pd.isna(atr.iloc[i]):
                continue

            if raw_lower.iloc[i] > final_lower.iloc[i - 1] or close.iloc[i - 1] < final_lower.iloc[i - 1]:
                final_lower.iloc[i] = raw_lower.iloc[i]
            else:
                final_lower.iloc[i] = final_lower.iloc[i - 1]

            if raw_upper.iloc[i] < final_upper.iloc[i - 1] or close.iloc[i - 1] > final_upper.iloc[i - 1]:
                final_upper.iloc[i] = raw_upper.iloc[i]
            else:
                final_upper.iloc[i] = final_upper.iloc[i - 1]

            prev_st = supertrend.iloc[i - 1]
            if pd.isna(prev_st):
                supertrend.iloc[i] = final_lower.iloc[i]
                direction.iloc[i] = 1.0
            elif prev_st == final_upper.iloc[i - 1]:
                if close.iloc[i] <= final_upper.iloc[i]:
                    supertrend.iloc[i] = final_upper.iloc[i]
                    direction.iloc[i] = -1.0
                else:
                    supertrend.iloc[i] = final_lower.iloc[i]
                    direction.iloc[i] = 1.0
            else:
                if close.iloc[i] >= final_lower.iloc[i]:
                    supertrend.iloc[i] = final_lower.iloc[i]
                    direction.iloc[i] = 1.0
                else:
                    supertrend.iloc[i] = final_upper.iloc[i]
                    direction.iloc[i] = -1.0

        return supertrend, direction
