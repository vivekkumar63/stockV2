from __future__ import annotations
import math
import numpy as np
import pandas as pd
from .models import Zone, ZoneLevel


class PriceStructureDetector:
    """Swing highs → supply levels; swing lows → demand levels."""

    def detect(self, df: pd.DataFrame, window: int = 10) -> list[ZoneLevel]:
        if len(df) < window * 2 + 1:
            return []
        levels: list[ZoneLevel] = []
        close = df["close"].to_numpy()
        high  = df["high"].to_numpy()
        low   = df["low"].to_numpy()
        n = len(df)
        last_demand_idx = last_supply_idx = -999

        for i in range(window, n - window):
            # Swing low (demand)
            sub_low = low[i - window:i + window + 1]
            if np.argmin(sub_low) == window:  # i is the unique minimum position
                if i - last_demand_idx >= 3:
                    # Estimate reaction: how much did price rally from this low
                    future_max = max(close[i:min(i + 20, n)]) if i + 1 < n else close[i]
                    reaction_pct = (future_max - low[i]) / low[i] * 100
                    volume_ratio = float(df["volume_ratio"].iloc[i]) if "volume_ratio" in df.columns else 1.0
                    levels.append(ZoneLevel(
                        price=float(low[i]),
                        zone_type="demand",
                        source_tag="swing_low",
                        strength_hint=min(1.0, reaction_pct / 10),
                        bar_index=i,
                        volume_ratio=volume_ratio if math.isfinite(volume_ratio) else 1.0,
                    ))
                    last_demand_idx = i

            # Swing high (supply)
            sub_high = high[i - window:i + window + 1]
            if np.argmax(sub_high) == window:  # i is the unique maximum position
                if i - last_supply_idx >= 3:
                    future_min = min(close[i:min(i + 20, n)]) if i + 1 < n else close[i]
                    reaction_pct = (high[i] - future_min) / high[i] * 100
                    volume_ratio = float(df["volume_ratio"].iloc[i]) if "volume_ratio" in df.columns else 1.0
                    levels.append(ZoneLevel(
                        price=float(high[i]),
                        zone_type="supply",
                        source_tag="swing_high",
                        strength_hint=min(1.0, reaction_pct / 10),
                        bar_index=i,
                        volume_ratio=volume_ratio if math.isfinite(volume_ratio) else 1.0,
                    ))
                    last_supply_idx = i

        return levels


class MADetector:
    """MA levels become zones if price bounced/rejected ≥2× in last 60 bars."""

    _MAS = [
        ("ema_9",   "ema_9"),
        ("ema_21",  "ema_21"),
        ("ema_50",  "ema_50"),
        ("sma_200", "sma_200"),
    ]

    def detect(self, df: pd.DataFrame) -> list[ZoneLevel]:
        if len(df) < 10:
            return []
        levels: list[ZoneLevel] = []
        price = float(df["close"].iloc[-1])
        n = len(df)
        close = df["close"].to_numpy()
        low   = df["low"].to_numpy()
        high  = df["high"].to_numpy()

        atr_arr = df["atr_14"].to_numpy() if "atr_14" in df.columns else None

        for col, tag in self._MAS:
            if col not in df.columns:
                continue
            ma_val = df[col].iloc[-1]
            if not math.isfinite(ma_val):
                continue
            ma_val = float(ma_val)
            if col == "sma_200" and len(df) < 200:
                continue
            ma_series = df[col].to_numpy()

            # Count bounces/rejections in last 60 bars using ATR-based tolerance
            lookback = min(60, n)
            touches = 0
            for i in range(n - lookback, n):
                if not math.isfinite(ma_series[i]):
                    continue
                if atr_arr is not None and math.isfinite(atr_arr[i]) and atr_arr[i] > 0:
                    tol = 0.5 * atr_arr[i]
                else:
                    tol = ma_series[i] * 0.01
                # Demand bounce: low touched MA (within tol) and close recovered above
                if low[i] <= ma_series[i] + tol and close[i] > ma_series[i]:
                    touches += 1
                # Supply rejection: high touched MA (within tol) and close fell below
                if high[i] >= ma_series[i] - tol and close[i] < ma_series[i]:
                    touches += 1

            if touches < 2:
                continue

            if price > ma_val:
                zone_type = "demand"
            else:
                zone_type = "supply"

            levels.append(ZoneLevel(
                price=ma_val,
                zone_type=zone_type,
                source_tag=tag,
                strength_hint=min(1.0, touches / 5),
                bar_index=n - 1,
            ))

        return levels


class VolumeDetector:
    """High-volume bars (vol ≥ 1.5× 20d avg) that preceded a directional move."""

    def detect(self, df: pd.DataFrame) -> list[ZoneLevel]:
        if len(df) < 22 or "volume_ratio" not in df.columns:
            return []
        levels: list[ZoneLevel] = []
        n = len(df)
        close = df["close"].to_numpy()
        vol_ratio = df["volume_ratio"].to_numpy()

        for i in range(1, n - 5):
            vr = vol_ratio[i]
            if not math.isfinite(vr) or vr < 1.5:
                continue
            if close[i] <= 0:
                continue
            future_close = close[min(i + 5, n - 1)]
            move_pct = (future_close - close[i]) / close[i] * 100
            if move_pct >= 1.5:
                levels.append(ZoneLevel(
                    price=float(close[i]),
                    zone_type="demand",
                    source_tag="vol_node",
                    strength_hint=min(1.0, abs(move_pct) / 10),
                    bar_index=i,
                    volume_ratio=float(vr),
                ))
            elif move_pct <= -1.5:
                levels.append(ZoneLevel(
                    price=float(close[i]),
                    zone_type="supply",
                    source_tag="vol_node",
                    strength_hint=min(1.0, abs(move_pct) / 10),
                    bar_index=i,
                    volume_ratio=float(vr),
                ))

        return levels


class VolatilityDetector:
    """Bollinger Bands: lower band → demand, upper band → supply.
    Only emit if current price is within 1×ATR of the band."""

    def detect(self, df: pd.DataFrame) -> list[ZoneLevel]:
        required = {"bb_lower", "bb_upper", "atr_14"}
        if len(df) < 20 or not required.issubset(df.columns):
            return []
        price = float(df["close"].iloc[-1])
        atr   = float(df["atr_14"].iloc[-1])
        if not math.isfinite(atr) or atr <= 0:
            return []

        levels: list[ZoneLevel] = []
        bb_lower = float(df["bb_lower"].iloc[-1])
        bb_upper = float(df["bb_upper"].iloc[-1])

        if math.isfinite(bb_lower) and abs(price - bb_lower) <= atr:
            levels.append(ZoneLevel(
                price=bb_lower,
                zone_type="demand",
                source_tag="bb_lower",
                strength_hint=0.5,
                bar_index=len(df) - 1,
            ))

        if math.isfinite(bb_upper) and abs(price - bb_upper) <= atr:
            levels.append(ZoneLevel(
                price=bb_upper,
                zone_type="supply",
                source_tag="bb_upper",
                strength_hint=0.5,
                bar_index=len(df) - 1,
            ))

        return levels


class MomentumDetector:
    """RSI oversold bounce → demand; RSI overbought rejection → supply."""

    def detect(self, df: pd.DataFrame) -> list[ZoneLevel]:
        if len(df) < 15 or "rsi_14" not in df.columns:
            return []
        levels: list[ZoneLevel] = []
        n = len(df)
        rsi = df["rsi_14"].to_numpy()
        close = df["close"].to_numpy()

        for i in range(1, n):
            if not math.isfinite(rsi[i]) or not math.isfinite(rsi[i - 1]):
                continue
            # Oversold bounce: RSI was < 35 and is now rising
            if rsi[i - 1] < 35 and rsi[i] > rsi[i - 1]:
                levels.append(ZoneLevel(
                    price=float(close[i]),
                    zone_type="demand",
                    source_tag="rsi_oversold",
                    strength_hint=min(1.0, (35 - rsi[i - 1]) / 35),
                    bar_index=i,
                ))
            # Overbought rejection: RSI was > 65 and is now falling
            if rsi[i - 1] > 65 and rsi[i] < rsi[i - 1]:
                levels.append(ZoneLevel(
                    price=float(close[i]),
                    zone_type="supply",
                    source_tag="rsi_overbought",
                    strength_hint=min(1.0, (rsi[i - 1] - 65) / 35),
                    bar_index=i,
                ))

        return levels


class FibonacciDetector:
    """Fibonacci retracement levels from the last major swing.
    Only emit if price reacted within 0.3×ATR of the level."""

    _FIBS = [0.236, 0.382, 0.5, 0.618, 0.786]

    def detect(self, df: pd.DataFrame) -> list[ZoneLevel]:
        if len(df) < 50 or "atr_14" not in df.columns:
            return []
        atr = float(df["atr_14"].iloc[-1])
        if not math.isfinite(atr) or atr <= 0:
            return []

        n = len(df)
        lookback = min(120, n)
        window = df.iloc[-lookback:]
        swing_high = float(window["high"].max())
        swing_low  = float(window["low"].min())
        rng = swing_high - swing_low
        if rng < atr:
            return []

        close_arr = df["close"].to_numpy()
        price_now = float(df["close"].iloc[-1])
        # Determine trend: uptrend if current price > midpoint
        uptrend = price_now > (swing_high + swing_low) / 2

        levels: list[ZoneLevel] = []
        for fib in self._FIBS:
            if uptrend:
                # Demand levels = retracements from high during uptrend
                fib_price = swing_high - fib * rng
                zone_type = "demand"
            else:
                # Supply levels = retracements from low during downtrend
                fib_price = swing_low + fib * rng
                zone_type = "supply"

            # Check if price reacted near this level in the last lookback
            reacted = False
            for i in range(n - lookback, n):
                if abs(close_arr[i] - fib_price) <= 0.3 * atr:
                    reacted = True
                    break
            if not reacted:
                continue

            tag = f"fib_{round(fib * 100, 1)}"  # e.g. "fib_61.8"
            levels.append(ZoneLevel(
                price=fib_price,
                zone_type=zone_type,
                source_tag=tag,
                strength_hint=0.6,
                bar_index=n - 1,
            ))

        return levels


class PivotPointDetector:
    """Classic floor trader pivot points (PP, R1-R3, S1-S3) from daily, weekly, and monthly OHLC.

    R levels → supply zones; S levels → demand zones; PP → zone type based on price position.
    Only emits levels within 10×ATR of current price to stay actionable.
    """

    @staticmethod
    def _calc(h: float, l: float, c: float) -> dict:
        pp = (h + l + c) / 3.0
        rng = h - l
        return {
            "supply": [2 * pp - l, pp + rng, h + 2 * (pp - l)],
            "demand": [2 * pp - h, pp - rng, l - 2 * (h - pp)],
            "pivot":  pp,
        }

    def _add(self, levels: list, computed: dict, tag: str, strength: float,
             bar_index: int, price: float, atr: float) -> None:
        max_dist = 10 * atr
        for lvl in computed["supply"]:
            if lvl > 0 and abs(lvl - price) <= max_dist:
                levels.append(ZoneLevel(price=lvl, zone_type="supply",
                                        source_tag=tag, strength_hint=strength, bar_index=bar_index))
        for lvl in computed["demand"]:
            if lvl > 0 and abs(lvl - price) <= max_dist:
                levels.append(ZoneLevel(price=lvl, zone_type="demand",
                                        source_tag=tag, strength_hint=strength, bar_index=bar_index))
        pp = computed["pivot"]
        if pp > 0 and abs(pp - price) <= max_dist:
            levels.append(ZoneLevel(
                price=pp,
                zone_type="demand" if price > pp else "supply",
                source_tag=tag, strength_hint=strength, bar_index=bar_index,
            ))

    def detect(self, df: pd.DataFrame) -> list[ZoneLevel]:
        if len(df) < 5 or "atr_14" not in df.columns:
            return []
        atr = float(df["atr_14"].iloc[-1])
        if not math.isfinite(atr) or atr <= 0:
            return []
        price = float(df["close"].iloc[-1])
        n = len(df)
        levels: list[ZoneLevel] = []

        # Daily pivot — previous complete bar
        if n >= 2:
            p = df.iloc[-2]
            self._add(levels, self._calc(float(p["high"]), float(p["low"]), float(p["close"])),
                      "daily_pivot", 0.50, n - 1, price, atr)

        # Weekly / monthly pivots — need date column
        if "date" not in df.columns:
            return levels

        df2 = df.copy()
        df2["_dt"] = pd.to_datetime(df2["date"])
        df2["_wk"] = df2["_dt"].dt.to_period("W")
        df2["_mo"] = df2["_dt"].dt.to_period("M")

        # Weekly pivot — last complete week
        cur_wk = df2["_wk"].iloc[-1]
        prev_wk = df2[df2["_wk"] < cur_wk]
        if not prev_wk.empty:
            last_wk = prev_wk[prev_wk["_wk"] == prev_wk["_wk"].iloc[-1]]
            wh = float(last_wk["high"].max())
            wl = float(last_wk["low"].min())
            wc = float(last_wk["close"].iloc[-1])
            self._add(levels, self._calc(wh, wl, wc), "weekly_pivot", 0.65, n - 1, price, atr)

        # Monthly pivot — last complete month
        cur_mo = df2["_mo"].iloc[-1]
        prev_mo = df2[df2["_mo"] < cur_mo]
        if not prev_mo.empty:
            last_mo = prev_mo[prev_mo["_mo"] == prev_mo["_mo"].iloc[-1]]
            mh = float(last_mo["high"].max())
            ml = float(last_mo["low"].min())
            mc = float(last_mo["close"].iloc[-1])
            self._add(levels, self._calc(mh, ml, mc), "monthly_pivot", 0.75, n - 1, price, atr)

        return levels


class Week52Detector:
    """52-week high/low as major supply/demand zones.

    52W high → supply (resistance); 52W low → demand (support).
    Always emitted — even if far away — since they are primary reference levels.
    """

    def detect(self, df: pd.DataFrame) -> list[ZoneLevel]:
        if len(df) < 50:
            return []
        n = len(df)
        bars_52w = min(250, n)

        if "high" not in df.columns or "low" not in df.columns:
            return []

        high_52w = float(df["high"].iloc[-bars_52w:].max())
        low_52w  = float(df["low"].iloc[-bars_52w:].min())

        levels: list[ZoneLevel] = []
        if high_52w > 0:
            levels.append(ZoneLevel(
                price=high_52w, zone_type="supply",
                source_tag="52w_high", strength_hint=0.85, bar_index=n - 1,
            ))
        if low_52w > 0:
            levels.append(ZoneLevel(
                price=low_52w, zone_type="demand",
                source_tag="52w_low", strength_hint=0.85, bar_index=n - 1,
            ))
        return levels


class CandlestickDetector:
    """Classic reversal candlestick patterns → zone levels for the last 30 bars.

    Each pattern emits a ZoneLevel at the bar's close price so the clusterer can
    merge it with nearby structural or MA zones for confluence.
    """

    def detect(self, df: pd.DataFrame) -> list[ZoneLevel]:
        if len(df) < 3:
            return []
        levels: list[ZoneLevel] = []
        n = len(df)
        lookback = min(30, n - 1)  # leave room for prev-bar access

        open_  = df["open"].to_numpy()
        high_  = df["high"].to_numpy()
        low_   = df["low"].to_numpy()
        close_ = df["close"].to_numpy()

        for i in range(n - lookback, n):
            o, h, l, c = open_[i], high_[i], low_[i], close_[i]
            if not (math.isfinite(o) and math.isfinite(h) and math.isfinite(l) and math.isfinite(c)):
                continue
            rng = h - l
            if rng <= 0:
                continue
            body = abs(c - o)
            upper_wick = h - max(o, c)
            lower_wick = min(o, c) - l
            body_ratio = body / rng

            # Doji: body < 10% of range → ambiguous; skip if far from S/R
            if body_ratio < 0.1:
                levels.append(ZoneLevel(price=float(c), zone_type="demand",
                                        source_tag="doji", strength_hint=0.3, bar_index=i))
                continue

            # Hammer (bullish): lower wick ≥ 2× body, upper wick ≤ 30% of body, any color
            if lower_wick >= 2 * body and upper_wick <= 0.3 * body:
                levels.append(ZoneLevel(price=float(l), zone_type="demand",
                                        source_tag="hammer", strength_hint=0.65, bar_index=i))
                continue

            # Shooting Star (bearish): upper wick ≥ 2× body, lower wick ≤ 30% of body
            if upper_wick >= 2 * body and lower_wick <= 0.3 * body:
                levels.append(ZoneLevel(price=float(h), zone_type="supply",
                                        source_tag="shooting_star", strength_hint=0.65, bar_index=i))
                continue

            # Engulfing patterns need previous bar
            if i == 0:
                continue
            po, pc = open_[i - 1], close_[i - 1]
            if not (math.isfinite(po) and math.isfinite(pc)):
                continue

            # Bullish engulfing: green bar fully engulfs previous red bar
            if c > o and pc < po and c >= po and o <= pc:
                levels.append(ZoneLevel(price=float(c), zone_type="demand",
                                        source_tag="bullish_engulfing", strength_hint=0.70, bar_index=i))
                continue

            # Bearish engulfing: red bar fully engulfs previous green bar
            if c < o and pc > po and c <= po and o >= pc:
                levels.append(ZoneLevel(price=float(c), zone_type="supply",
                                        source_tag="bearish_engulfing", strength_hint=0.70, bar_index=i))

        return levels


class PrevHighLowDetector:
    """Previous day, week, and month raw H/L as institutional S/R levels.

    These are different from calculated pivot points — they are exact price levels
    where buyers/sellers actually transacted, making them strong institutional references.
    """

    def detect(self, df: pd.DataFrame) -> list[ZoneLevel]:
        if len(df) < 5 or "date" not in df.columns:
            return []
        n = len(df)

        df2 = df.copy()
        df2["_dt"] = pd.to_datetime(df2["date"])
        df2["_wk"] = df2["_dt"].dt.to_period("W")
        df2["_mo"] = df2["_dt"].dt.to_period("M")

        levels: list[ZoneLevel] = []

        # Previous day H/L (strength 0.55 — less reliable than weekly/monthly)
        if n >= 2:
            pd_row = df.iloc[-2]
            levels.append(ZoneLevel(price=float(pd_row["high"]), zone_type="supply",
                                    source_tag="prev_day_high", strength_hint=0.55, bar_index=n - 1))
            levels.append(ZoneLevel(price=float(pd_row["low"]), zone_type="demand",
                                    source_tag="prev_day_low", strength_hint=0.55, bar_index=n - 1))

        # Previous week H/L (strength 0.70)
        cur_wk = df2["_wk"].iloc[-1]
        prev_wk_df = df2[df2["_wk"] < cur_wk]
        if not prev_wk_df.empty:
            last_wk = prev_wk_df[prev_wk_df["_wk"] == prev_wk_df["_wk"].iloc[-1]]
            wh = float(last_wk["high"].max())
            wl = float(last_wk["low"].min())
            levels.append(ZoneLevel(price=wh, zone_type="supply",
                                    source_tag="prev_week_high", strength_hint=0.70, bar_index=n - 1))
            levels.append(ZoneLevel(price=wl, zone_type="demand",
                                    source_tag="prev_week_low", strength_hint=0.70, bar_index=n - 1))

        # Previous month H/L (strength 0.80)
        cur_mo = df2["_mo"].iloc[-1]
        prev_mo_df = df2[df2["_mo"] < cur_mo]
        if not prev_mo_df.empty:
            last_mo = prev_mo_df[prev_mo_df["_mo"] == prev_mo_df["_mo"].iloc[-1]]
            mh = float(last_mo["high"].max())
            ml = float(last_mo["low"].min())
            levels.append(ZoneLevel(price=mh, zone_type="supply",
                                    source_tag="prev_month_high", strength_hint=0.80, bar_index=n - 1))
            levels.append(ZoneLevel(price=ml, zone_type="demand",
                                    source_tag="prev_month_low", strength_hint=0.80, bar_index=n - 1))

        return levels


class TrendlineDetector:
    """Diagonal trendlines from swing pivot points.

    Detects descending/horizontal resistance (supply) and ascending/horizontal
    support (demand) trendlines. Emits a ZoneLevel at the current trendline price
    so the clusterer can merge it with nearby horizontal zones for confluence.
    """

    PIVOT_WINDOW    = 7    # bars on each side to qualify a pivot
    LOOKBACK        = 150  # max bars to scan for pivots
    MIN_PIVOT_GAP   = 10   # min bars between two pivots on the same line
    MAX_VIOLATIONS  = 1    # max closes on wrong side of line before it's invalidated

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _linreg(xs: list, ys: list) -> tuple[float, float]:
        n = len(xs)
        sx  = sum(xs);  sy  = sum(ys)
        sxy = sum(x * y for x, y in zip(xs, ys))
        sxx = sum(x * x for x in xs)
        d = n * sxx - sx * sx
        if abs(d) < 1e-10:
            return 0.0, sy / n
        slope = (n * sxy - sx * sy) / d
        return slope, (sy - slope * sx) / n

    def _find_pivots(self, arr: np.ndarray, kind: str) -> list[int]:
        """Return bar indices of pivot highs ('high') or pivot lows ('low')."""
        w, n = self.PIVOT_WINDOW, len(arr)
        pivots: list[int] = []
        for i in range(w, n - w):
            if pivots and i - pivots[-1] < self.MIN_PIVOT_GAP:
                continue
            sub = arr[i - w: i + w + 1]
            if kind == "high" and np.argmax(sub) == w:
                pivots.append(i)
            elif kind == "low" and np.argmin(sub) == w:
                pivots.append(i)
        return pivots

    def _best_line(
        self,
        pivots: list[int],
        pivot_arr: np.ndarray,   # high[] for resistance, low[] for support
        close_arr: np.ndarray,
        atr: float,
        kind: str,               # "high" → resistance/supply, "low" → support/demand
    ) -> tuple[float, float, int] | None:
        """Try pairs of pivots (newest first). Return (slope, intercept, touches) or None."""
        best: tuple[float, float, int] | None = None
        m = len(pivot_arr)

        for i in range(len(pivots) - 1, 0, -1):
            p2, p1 = pivots[i], pivots[i - 1]
            slope, intercept = self._linreg([p1, p2], [pivot_arr[p1], pivot_arr[p2]])

            violations = 0
            touches    = 2   # the two anchor pivots count
            for j in range(p1 + 1, m):
                tl = slope * j + intercept
                if not math.isfinite(tl) or tl <= 0:
                    continue
                if kind == "high":
                    if close_arr[j] > tl + 0.15 * atr:
                        violations += 1
                    elif pivot_arr[j] >= tl - atr:   # high came within 1 ATR
                        touches += 1
                else:
                    if close_arr[j] < tl - 0.15 * atr:
                        violations += 1
                    elif pivot_arr[j] <= tl + atr:
                        touches += 1
                if violations > self.MAX_VIOLATIONS:
                    break

            if violations <= self.MAX_VIOLATIONS and touches >= 2:
                if best is None or touches > best[2]:
                    best = (slope, intercept, touches)
        return best

    # ── public ───────────────────────────────────────────────────────────────

    def detect(self, df: pd.DataFrame) -> list[ZoneLevel]:
        n = len(df)
        if n < self.PIVOT_WINDOW * 2 + 20:
            return []

        atr = float(df["atr_14"].iloc[-1]) if "atr_14" in df.columns else 0.0
        if not math.isfinite(atr) or atr <= 0:
            atr = float(df["close"].iloc[-1]) * 0.01

        lb   = max(0, n - self.LOOKBACK)
        h_lb = df["high"].to_numpy()[lb:]
        l_lb = df["low"].to_numpy()[lb:]
        c_lb = df["close"].to_numpy()[lb:]
        m    = len(h_lb)
        price = float(c_lb[-1])

        levels: list[ZoneLevel] = []

        # ── Resistance trendline (pivot highs → supply) ───────────────────
        ph = self._find_pivots(h_lb, "high")
        if len(ph) >= 2:
            res = self._best_line(ph, h_lb, c_lb, atr, "high")
            if res:
                slope, intercept, touches = res
                tl_price = slope * (m - 1) + intercept
                if (math.isfinite(tl_price) and tl_price > 0
                        and abs(tl_price - price) <= 15 * atr):
                    strength = min(0.85, 0.60 + (touches - 2) * 0.07)
                    levels.append(ZoneLevel(
                        price=round(tl_price, 4),
                        zone_type="supply",
                        source_tag="trendline_resistance",
                        strength_hint=strength,
                        bar_index=n - 1,
                    ))

        # ── Support trendline (pivot lows → demand) ───────────────────────
        pl = self._find_pivots(l_lb, "low")
        if len(pl) >= 2:
            res = self._best_line(pl, l_lb, c_lb, atr, "low")
            if res:
                slope, intercept, touches = res
                tl_price = slope * (m - 1) + intercept
                if (math.isfinite(tl_price) and tl_price > 0
                        and abs(tl_price - price) <= 15 * atr):
                    strength = min(0.85, 0.60 + (touches - 2) * 0.07)
                    levels.append(ZoneLevel(
                        price=round(tl_price, 4),
                        zone_type="demand",
                        source_tag="trendline_support",
                        strength_hint=strength,
                        bar_index=n - 1,
                    ))

        return levels


class VWAPZoneDetector:
    """Intraday VWAP from 5-min bars → one demand or supply zone at current VWAP level."""

    def detect(
        self,
        symbol: str,
        db,           # Session — typed loosely to avoid circular import in tests
        *,
        atr: float,
        current_price: float | None = None,
    ) -> list[Zone]:
        from sqlalchemy import text as _text

        rows = db.execute(_text("""
            SELECT datetime, high, low, close, volume
            FROM intraday_prices_5m
            WHERE symbol = :s AND datetime::date = CURRENT_DATE
            ORDER BY datetime ASC
        """), {"s": symbol}).fetchall()

        if len(rows) < 6:
            return []

        valid_rows = [r for r in rows if r[1] is not None and r[2] is not None and r[3] is not None
                      and math.isfinite(float(r[1])) and math.isfinite(float(r[2])) and math.isfinite(float(r[3]))]
        if len(valid_rows) < 6:
            return []
        highs   = [float(r[1]) for r in valid_rows]
        lows    = [float(r[2]) for r in valid_rows]
        closes  = [float(r[3]) for r in valid_rows]
        volumes = [max(float(r[4]), 1.0) if r[4] is not None else 1.0 for r in valid_rows]

        typical = [(h + l + c) / 3.0 for h, l, c in zip(highs, lows, closes)]
        cum_tv  = 0.0
        cum_v   = 0.0
        for tp, v in zip(typical, volumes):
            cum_tv += tp * v
            cum_v  += v
        if cum_v == 0:
            return []
        vwap = cum_tv / cum_v

        band_low  = vwap - 0.3 * atr
        band_high = vwap + 0.3 * atr

        price = current_price if current_price is not None else closes[-1]
        zone_type = "demand" if price > vwap else "supply"

        return [Zone(
            low=band_low,
            high=band_high,
            zone_type=zone_type,
            source_tags=["vwap"],
            touch_count=0,
            last_reaction_pct=0.0,
            freshness="fresh",
            volume_at_zone=1.0,
            bar_index=len(rows) - 1,
            strength_hint=0.6,
            source="vwap",
        )]


class IchimokuCloudDetector:
    """Ichimoku Cloud (Kumo) as supply/demand zones + Kijun-sen as standalone S/R.

    Price above cloud → cloud is demand support below.
    Price below cloud → cloud is resistance above (supply).
    Price inside cloud → ambiguous, skip.
    Kijun-sen emitted when within 8% of current price.
    """

    def detect(self, df: pd.DataFrame) -> list[ZoneLevel]:
        if len(df) < 52:
            return []

        span_a_col = (
            "ichimoku_span_a" if "ichimoku_span_a" in df.columns
            else "ichimoku_cloud_a" if "ichimoku_cloud_a" in df.columns
            else None
        )
        span_b_col = (
            "ichimoku_span_b" if "ichimoku_span_b" in df.columns
            else "ichimoku_cloud_b" if "ichimoku_cloud_b" in df.columns
            else None
        )
        if span_a_col is None or span_b_col is None or "ichimoku_kijun" not in df.columns:
            return []

        n = len(df)
        price  = float(df["close"].iloc[-1])
        atr    = float(df["atr_14"].iloc[-1]) if "atr_14" in df.columns else price * 0.01
        if not math.isfinite(atr) or atr <= 0:
            atr = price * 0.01

        span_a = float(df[span_a_col].iloc[-1])
        span_b = float(df[span_b_col].iloc[-1])
        kijun  = float(df["ichimoku_kijun"].iloc[-1])

        if not (math.isfinite(span_a) and math.isfinite(span_b) and span_a > 0 and span_b > 0):
            return []

        cloud_top = max(span_a, span_b)
        cloud_bot = min(span_a, span_b)
        bullish_cloud = span_a > span_b

        thickness_atr   = (cloud_top - cloud_bot) / atr
        thickness_bonus = min(0.20, thickness_atr * 0.05)

        levels: list[ZoneLevel] = []

        if price > cloud_top:
            direction_bonus = 0.10 if bullish_cloud else 0.0
            strength = min(0.80, 0.45 + thickness_bonus + direction_bonus)
            levels.append(ZoneLevel(price=cloud_top, zone_type="demand",
                                    source_tag="ichimoku_cloud", strength_hint=strength,
                                    bar_index=n - 1))
            levels.append(ZoneLevel(price=cloud_bot, zone_type="demand",
                                    source_tag="ichimoku_cloud", strength_hint=round(strength * 0.9, 3),
                                    bar_index=n - 1))

        elif price < cloud_bot:
            direction_bonus = 0.10 if not bullish_cloud else 0.0
            strength = min(0.80, 0.45 + thickness_bonus + direction_bonus)
            levels.append(ZoneLevel(price=cloud_bot, zone_type="supply",
                                    source_tag="ichimoku_cloud", strength_hint=strength,
                                    bar_index=n - 1))
            levels.append(ZoneLevel(price=cloud_top, zone_type="supply",
                                    source_tag="ichimoku_cloud", strength_hint=round(strength * 0.9, 3),
                                    bar_index=n - 1))
        # else: price inside cloud → ambiguous, emit nothing

        if math.isfinite(kijun) and kijun > 0:
            dist_pct = abs(price - kijun) / price * 100
            if dist_pct <= 8.0:
                kijun_type = "demand" if price > kijun else "supply"
                levels.append(ZoneLevel(price=kijun, zone_type=kijun_type,
                                        source_tag="ichimoku_kijun", strength_hint=0.60,
                                        bar_index=n - 1))

        return levels
