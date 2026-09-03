from __future__ import annotations
from .models import Zone, LongSetup, ShortSetup


class EntryEngine:

    def compute_long(
        self,
        demand_zone: Zone,
        supply_zones: list[Zone],
        atr: float,
        rsi: float = 50.0,
        trend: str = "sideways",
        n_bars: int = 500,
    ) -> LongSetup:
        ideal = demand_zone.midpoint
        aggressive = demand_zone.high
        conservative = demand_zone.low - 0.2 * atr
        sl = round(demand_zone.low - 0.3 * atr, 2)

        # Targets: use supply zones sorted by low ascending
        supply_above = sorted(
            [z for z in supply_zones if z.low > ideal and (z.low - ideal) <= 5 * atr],
            key=lambda z: z.low,
        )

        def _rr(target: float) -> float:
            denom = ideal - sl
            if denom <= 0:
                return 0.0
            return round((target - ideal) / denom, 2)

        t1 = round(supply_above[0].low, 2) if supply_above else round(ideal + 2 * atr, 2)
        t2 = round(supply_above[1].low, 2) if len(supply_above) > 1 else round(ideal + 4 * atr, 2)
        t3 = round(supply_above[2].low, 2) if len(supply_above) > 2 else round(ideal + 6 * atr, 2)

        score = self._long_score(demand_zone, _rr(t1), trend, rsi)
        explanation = self._long_explanation(demand_zone, ideal, sl, t1, _rr(t1), t2, atr)
        invalidation = f"Invalidated if close below ₹{sl:,.2f} on above-average volume"

        return LongSetup(
            score=score,
            ideal_entry=round(ideal, 2),
            aggressive_entry=round(aggressive, 2),
            conservative_entry=round(conservative, 2),
            stop_loss=sl,
            t1=t1, t1_rr=_rr(t1),
            t2=t2, t2_rr=_rr(t2),
            t3=t3, t3_rr=_rr(t3),
            explanation=explanation,
            invalidation=invalidation,
        )

    def compute_short(
        self,
        supply_zone: Zone,
        demand_zones: list[Zone],
        atr: float,
        rsi: float = 50.0,
        trend: str = "sideways",
        n_bars: int = 500,
    ) -> ShortSetup:
        ideal = supply_zone.midpoint
        aggressive = supply_zone.low
        conservative = supply_zone.high + 0.2 * atr
        sl = round(supply_zone.high + 0.3 * atr, 2)

        demand_below = sorted(
            [z for z in demand_zones if z.high < ideal and (ideal - z.high) <= 5 * atr],
            key=lambda z: z.high, reverse=True,
        )

        def _rr(target: float) -> float:
            denom = sl - ideal
            if denom <= 0:
                return 0.0
            return round((ideal - target) / denom, 2)

        t1 = round(demand_below[0].high, 2) if demand_below else round(ideal - 2 * atr, 2)
        t2 = round(demand_below[1].high, 2) if len(demand_below) > 1 else round(ideal - 4 * atr, 2)
        t3 = round(demand_below[2].high, 2) if len(demand_below) > 2 else round(ideal - 6 * atr, 2)

        score = self._short_score(supply_zone, _rr(t1), trend, rsi)
        explanation = self._short_explanation(supply_zone, ideal, sl, t1, _rr(t1), t2, atr)
        invalidation = f"Invalidated if close above ₹{sl:,.2f} on above-average volume"

        return ShortSetup(
            score=score,
            ideal_entry=round(ideal, 2),
            aggressive_entry=round(aggressive, 2),
            conservative_entry=round(conservative, 2),
            stop_loss=sl,
            t1=t1, t1_rr=_rr(t1),
            t2=t2, t2_rr=_rr(t2),
            t3=t3, t3_rr=_rr(t3),
            explanation=explanation,
            invalidation=invalidation,
        )

    # ── Scoring helpers ────────────────────────────────────────────────────────

    def _long_score(self, zone: Zone, best_rr: float, trend: str, rsi: float) -> int:
        # Zone strength 40%, R:R 30%, trend alignment 20%, RSI 10%
        zone_pts  = int(zone.score * 0.4)
        rr_pts    = min(30, int(max(0.0, min(best_rr, 5.0)) / 5.0 * 30))
        trend_pts = 20 if trend == "bullish" else 10 if trend == "sideways" else 0
        rsi_pts   = min(10, int(max(0.0, (50 - rsi)) / 50.0 * 10)) if rsi < 50 else 0
        return min(100, zone_pts + rr_pts + trend_pts + rsi_pts)

    def _short_score(self, zone: Zone, best_rr: float, trend: str, rsi: float) -> int:
        zone_pts  = int(zone.score * 0.4)
        rr_pts    = min(30, int(max(0.0, min(best_rr, 5.0)) / 5.0 * 30))
        trend_pts = 20 if trend == "bearish" else 10 if trend == "sideways" else 0
        rsi_pts   = min(10, int(max(0.0, (rsi - 50)) / 50.0 * 10)) if rsi > 50 else 0
        return min(100, zone_pts + rr_pts + trend_pts + rsi_pts)

    def _long_explanation(self, zone: Zone, entry: float, sl: float,
                           t1: float, rr: float, t2: float, atr: float) -> str:
        tags = ", ".join(zone.source_tags[:3]) if zone.source_tags else "price structure"
        return (
            f"Price in/near a {zone.freshness} demand zone "
            f"(₹{zone.low:,.0f}–₹{zone.high:,.0f}) supported by {tags}. "
            f"Entry at ₹{entry:,.0f} with SL ₹{sl:,.0f}, "
            f"first target ₹{t1:,.0f} (R:R 1:{rr}), second target ₹{t2:,.0f}."
        )

    def _short_explanation(self, zone: Zone, entry: float, sl: float,
                            t1: float, rr: float, t2: float, atr: float) -> str:
        tags = ", ".join(zone.source_tags[:3]) if zone.source_tags else "price structure"
        return (
            f"Price in/near a {zone.freshness} supply zone "
            f"(₹{zone.low:,.0f}–₹{zone.high:,.0f}) confirmed by {tags}. "
            f"Short entry at ₹{entry:,.0f} with SL ₹{sl:,.0f}, "
            f"first target ₹{t1:,.0f} (R:R 1:{rr})."
        )
