"""
RSI Oversold + MACD Crossover Swing Strategy

Entry (all 5 required):
  1. Trend    : EMA20 > EMA50 (bullish trend)
  2. RSI      : RSI14 < 30 AND rising (oversold + recovering)
  3. Pattern  : Bullish Engulfing OR Hammer candlestick
  4. MACD     : MACD line crosses above Signal line
  5. Volume   : Volume above 20-day average while price closes higher

Exit (any one sufficient):
  1. RSI      : RSI14 > 70 (overbought)
  2. Resistance: Close >= 99% of previous 20-bar high (near prior resistance)
  3. Stop loss: Close < swing low of last 10 bars (most recent swing low)
"""

import pandas as pd

from domains.special_strategies.base import SpecialBaseStrategy, SpecialSignal


def _detect_pattern(df: pd.DataFrame) -> str | None:
    """Return 'Bullish Engulfing' or 'Hammer' if present on the last bar, else None."""
    if len(df) < 2:
        return None
    o, c, h, lo = df["open"].iloc[-1], df["close"].iloc[-1], df["high"].iloc[-1], df["low"].iloc[-1]
    po, pc = df["open"].iloc[-2], df["close"].iloc[-2]
    if any(pd.isna(v) for v in [o, c, h, lo, po, pc]):
        return None

    # Bullish Engulfing: prior bar red, current bar green, body fully engulfs prior body
    if pc < po and c > o and o <= pc and c >= po:
        return "Bullish Engulfing"

    # Hammer: lower shadow ≥ 2× body, upper shadow ≤ 0.5× body (any colour)
    body = abs(c - o)
    lower_shadow = min(o, c) - lo
    upper_shadow = h - max(o, c)
    if body > 0 and lower_shadow >= 2 * body and upper_shadow <= 0.5 * body:
        return "Hammer"

    return None


class RsiMacdSwingStrategy(SpecialBaseStrategy):
    name = "RSI Oversold + MACD Swing"
    description = (
        "Buy: EMA20 > EMA50 (uptrend), RSI14 < 30 and rising, Bullish Engulfing or Hammer, "
        "MACD crosses above signal, volume above average. "
        "Sell: RSI14 > 70 (overbought), or price near prior 20-bar high, or below recent swing low."
    )

    def buy_signal(self, df: pd.DataFrame) -> SpecialSignal:
        if len(df) < 52:
            return SpecialSignal("NONE")

        close = df["close"]
        volume = df["volume"]

        # EMA20 computed inline for accuracy (ema_21 is close but not exact)
        ema20 = close.ewm(span=20, adjust=False).mean()
        ema50 = close.ewm(span=50, adjust=False).mean()
        curr_ema20, curr_ema50 = ema20.iloc[-1], ema50.iloc[-1]

        curr_rsi  = df["rsi_14"].iloc[-1]
        prev_rsi  = df["rsi_14"].iloc[-2]
        curr_macd = df["macd"].iloc[-1]
        prev_macd = df["macd"].iloc[-2]
        curr_sig  = df["macd_signal"].iloc[-1]
        prev_sig  = df["macd_signal"].iloc[-2]
        curr_close = close.iloc[-1]
        prev_close = close.iloc[-2]
        curr_vol   = volume.iloc[-1]
        vol_sma20  = df["volume_sma_20"].iloc[-1]

        if any(pd.isna(v) for v in [
            curr_ema20, curr_ema50, curr_rsi, prev_rsi,
            curr_macd, prev_macd, curr_sig, prev_sig,
            curr_close, prev_close, curr_vol, vol_sma20,
        ]):
            return SpecialSignal("NONE")

        met: list[str] = []
        failed: list[str] = []

        # 1. Trend: EMA20 > EMA50
        if curr_ema20 > curr_ema50:
            met.append(f"EMA20({curr_ema20:.2f}) > EMA50({curr_ema50:.2f})")
        else:
            failed.append(f"EMA20({curr_ema20:.2f}) <= EMA50({curr_ema50:.2f}) — no uptrend")

        # 2. RSI < 30 and rising
        if curr_rsi < 30 and curr_rsi > prev_rsi:
            met.append(f"RSI14({curr_rsi:.1f}) oversold and rising from {prev_rsi:.1f}")
        else:
            failed.append(f"RSI14({curr_rsi:.1f}) not oversold+rising (prev {prev_rsi:.1f})")

        # 3. Bullish Engulfing or Hammer
        pattern = _detect_pattern(df)
        if pattern:
            met.append(pattern)
        else:
            failed.append("No Bullish Engulfing or Hammer on last bar")

        # 4. MACD crosses above signal
        if prev_macd <= prev_sig and curr_macd > curr_sig:
            met.append(f"MACD({curr_macd:.4f}) crossed above Signal({curr_sig:.4f})")
        else:
            failed.append(f"MACD({curr_macd:.4f}) not crossing above Signal({curr_sig:.4f})")

        # 5. Volume above average while price rises
        if curr_vol > vol_sma20 and curr_close > prev_close:
            met.append(f"Volume({curr_vol:.0f}) > SMA20({vol_sma20:.0f}) with price up")
        else:
            failed.append(f"Volume not confirming (vol={curr_vol:.0f}, sma={vol_sma20:.0f})")

        if failed:
            return SpecialSignal("NONE", conditions_met=met, conditions_failed=failed)

        return SpecialSignal(
            signal_type="BUY",
            confidence=0.82,
            conditions_met=met,
            conditions_failed=[],
        )

    def sell_signal(self, df: pd.DataFrame, entry_price: float | None = None) -> bool:
        if len(df) < 5:
            return False

        curr_close = df["close"].iloc[-1]
        curr_rsi   = df["rsi_14"].iloc[-1]
        if pd.isna(curr_close):
            return False

        # 1. RSI overbought
        if not pd.isna(curr_rsi) and curr_rsi > 70:
            return True

        # 2. Near resistance — within 1% of previous 20-bar high
        lookback = min(20, len(df) - 1)
        prev_high = df["high"].iloc[-(lookback + 1):-1].max()
        if not pd.isna(prev_high) and curr_close >= prev_high * 0.99:
            return True

        # 3. Close below most recent swing low (lowest low of last 10 bars)
        sw_lookback = min(10, len(df) - 1)
        swing_low = df["low"].iloc[-(sw_lookback + 1):-1].min()
        if not pd.isna(swing_low) and curr_close < swing_low:
            return True

        return False
