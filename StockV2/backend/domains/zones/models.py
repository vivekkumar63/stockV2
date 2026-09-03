from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ZoneLevel:
    """A single raw price level emitted by one detector."""
    price: float
    zone_type: str           # "demand" | "supply"
    source_tag: str          # e.g. "swing_low", "ema_50", "vol_node", "fib_61.8"
    strength_hint: float     # 0–1 hint from detector (used in scoring)
    timeframe: str = "daily" # "daily" | "weekly"
    bar_index: int = -1      # index in df where level was detected (for recency)
    volume_ratio: float = 1.0  # volume ratio at detection bar


@dataclass
class Zone:
    """A clustered zone after merging nearby ZoneLevels."""
    low: float
    high: float
    zone_type: str           # "demand" | "supply"
    source_tags: list[str] = field(default_factory=list)
    touch_count: int = 0
    last_reaction_pct: float = 0.0
    freshness: str = "fresh" # "fresh" | "tested" | "weakened"
    score: int = 0           # filled by ZoneScorer
    volume_at_zone: float = 1.0
    bar_index: int = -1      # most recent bar_index among merged levels
    strength_hint: float = 0.5

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2.0


@dataclass
class LongSetup:
    score: int
    ideal_entry: float
    aggressive_entry: float
    conservative_entry: float
    stop_loss: float
    t1: float
    t1_rr: float
    t2: float
    t2_rr: float
    t3: float
    t3_rr: float
    explanation: str
    invalidation: str


@dataclass
class ShortSetup:
    score: int
    ideal_entry: float
    aggressive_entry: float
    conservative_entry: float
    stop_loss: float
    t1: float
    t1_rr: float
    t2: float
    t2_rr: float
    t3: float
    t3_rr: float
    explanation: str
    invalidation: str


@dataclass
class ZoneResult:
    symbol: str
    demand_zones: list[Zone] = field(default_factory=list)
    supply_zones: list[Zone] = field(default_factory=list)
    long_setup: Optional[LongSetup] = None
    short_setup: Optional[ShortSetup] = None
    market_structure: str = "sideways"  # "bullish" | "bearish" | "sideways"
    atr: float = 0.0
    rvol: float = 1.0
    price: float = 0.0
    position_tag: str = "neutral"
