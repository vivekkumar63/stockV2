from __future__ import annotations
from .models import Zone, ZoneLevel


class ZoneClusterer:
    def cluster(self, levels: list[ZoneLevel], atr: float) -> list[Zone]:
        """Merge nearby ZoneLevels (within 0.5×ATR) into Zones."""
        if not levels or atr <= 0:
            return []

        demand = sorted([l for l in levels if l.zone_type == "demand"], key=lambda l: l.price)
        supply = sorted([l for l in levels if l.zone_type == "supply"], key=lambda l: l.price)

        return self._merge(demand, atr, "demand") + self._merge(supply, atr, "supply")

    def _merge(self, sorted_levels: list[ZoneLevel], atr: float, zone_type: str) -> list[Zone]:
        if not sorted_levels:
            return []
        threshold = 0.5 * atr
        groups: list[list[ZoneLevel]] = []
        current_group = [sorted_levels[0]]

        for lvl in sorted_levels[1:]:
            if lvl.price - current_group[0].price <= threshold:
                current_group.append(lvl)
            else:
                groups.append(current_group)
                current_group = [lvl]
        groups.append(current_group)

        zones: list[Zone] = []
        for grp in groups:
            prices = [l.price for l in grp]
            min_p, max_p = min(prices), max(prices)
            source_tags = list(dict.fromkeys(l.source_tag for l in grp))  # dedup, preserve order
            avg_strength = sum(l.strength_hint for l in grp) / len(grp)
            best_bar    = max(l.bar_index for l in grp)
            avg_vol_ratio = sum(l.volume_ratio for l in grp) / len(grp)

            # Approximate touch count from number of overlapping levels
            touch_count = max(0, len(grp) - 1)
            if touch_count <= 1:
                freshness = "fresh"
            elif touch_count <= 3:
                freshness = "tested"
            else:
                freshness = "weakened"

            # last_reaction_pct: average strength_hint * 10 as a reaction proxy (0–10 range)
            last_reaction_pct = round(avg_strength * 10, 2)

            zones.append(Zone(
                low=round(min_p - 0.1 * atr, 2),
                high=round(max_p + 0.1 * atr, 2),
                zone_type=zone_type,
                source_tags=source_tags,
                touch_count=touch_count,
                last_reaction_pct=last_reaction_pct,
                freshness=freshness,
                volume_at_zone=avg_vol_ratio,
                bar_index=best_bar,
                strength_hint=avg_strength,
            ))

        return zones
