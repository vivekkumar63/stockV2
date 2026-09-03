from __future__ import annotations
import dataclasses
import math
from .models import Zone

# Tags that are correlated (EMA family) — counted as max 1 unique source each group
_CORRELATED_GROUPS = [
    {"ema_9", "ema_21"},
    {"ema_50", "sma_200"},
]


def _count_unique_sources(tags: list[str]) -> int:
    """Count independent confirmations, applying correlated-indicator guard."""
    counted: set[str] = set()
    merged: set[str] = set()
    for tag in tags:
        for group in _CORRELATED_GROUPS:
            if tag in group:
                representative = min(group)  # e.g. "ema_21"
                if representative not in merged:
                    merged.add(representative)
                    counted.add(representative)
                break
        else:
            counted.add(tag)
    return len(counted)


class ZoneScorer:
    """Score each Zone 0–100 from 6 independent components."""

    def score(self, zone: Zone, *, atr: float, n_bars: int, price: float) -> Zone:
        """Return a copy of zone with `.score` filled."""
        s = 0

        # 1. Confirmations (0–30): unique independent source tags
        unique = _count_unique_sources(zone.source_tags)
        s += min(30, unique * 8)

        # 2. Reaction quality (0–20): last_reaction_pct; 10% reaction → full 20 pts
        s += min(20, max(0, int(zone.last_reaction_pct / 10 * 20)))

        # 3. Volume at zone (0–15): volume_ratio; 3× = full
        vol = zone.volume_at_zone if math.isfinite(zone.volume_at_zone) else 1.0
        s += min(15, max(0, int((vol - 1.0) / 2.0 * 15)))

        # 4. Timeframe weight (0–15): all Phase A zones are daily → full 15 pts
        s += 15  # weekly zones (Phase B) will add differentiation later

        # 5. Recency (0–10): more recent bar_index = higher
        if n_bars > 0 and zone.bar_index >= 0:
            recency = zone.bar_index / n_bars
            s += round(recency * 10)

        # 6. ATR proximity (0–10): price within 2 ATR of zone midpoint
        if atr > 0:
            dist = abs(price - zone.midpoint)
            proximity = max(0.0, 1.0 - dist / (2 * atr))
            s += int(proximity * 10)

        return dataclasses.replace(zone, score=min(100, max(0, s)))

    def score_all(self, zones: list[Zone], *, atr: float, n_bars: int, price: float) -> list[Zone]:
        return [self.score(z, atr=atr, n_bars=n_bars, price=price) for z in zones]
