"""
Opportunity score (0–100) for a BUY signal.

Component weights:
  historical_win_rate   20  — backtest win rate for this (symbol, strategy) pair
  strategy_confidence   16  — confidence score from signal generation (0–1)
  regime_alignment      14  — how buy-friendly is the current market regime
  mtf_alignment         13  — multi-timeframe trend alignment score (0–1)
  volume                 9  — volume confirmation (normalised 0–1)
  sr_context             7  — proximity to support vs resistance (normalised 0–1)
  regime_strategy        4  — strategy's historical win rate in the current regime
  ml_signal_probability  7  — ML model probability that signal will be profitable
  sector_health         10  — sector rotation health score (0–100 from sector_breadth_daily)
  ── total ────────── 100

Quick mode (scanner): only win_rate, confidence, regime_alignment, regime_strategy
  (sum = 54; normalised to full scale when partial components are absent)

Full mode (on-demand endpoint): all 9 components.
"""

from dataclasses import dataclass, field
from typing import Optional

# How buy-friendly each regime is (1.0 = best, 0.0 = worst for longs)
_REGIME_BUY_SCORE: dict[str, float] = {
    "STRONG_BULL":     1.00,
    "BULL":            0.80,
    "SIDEWAYS":        0.50,
    "HIGH_VOLATILITY": 0.35,
    "BEAR":            0.20,
    "STRONG_BEAR":     0.00,
}

_WEIGHTS: dict[str, int] = {
    "historical_win_rate":   20,   # was 22
    "strategy_confidence":   16,   # was 18
    "regime_alignment":      14,   # was 16
    "mtf_alignment":         13,   # was 14
    "volume":                 9,   # was 10
    "sr_context":             7,   # was 8
    "regime_strategy":        4,
    "ml_signal_probability":  7,   # was 8
    "sector_health":         10,   # replaced index_alignment
    # false_signal_safety: inverted false-signal rate; included in full_score only
    # Weight not in this dict — applied as a flat multiplier after base score
}


def _grade(score: int) -> str:
    if score >= 80:
        return "A+"
    if score >= 65:
        return "A"
    if score >= 50:
        return "B"
    if score >= 35:
        return "C"
    return "D"


@dataclass
class OpportunityScore:
    symbol: str
    strategy_id: Optional[int]
    score: int         # 0–100
    grade: str         # A+ / A / B / C / D
    breakdown: dict = field(default_factory=dict)   # component raw 0–1 values


class OpportunityScorer:
    """
    Combines multiple intelligence signals into a single 0–100 opportunity score.

    Quick mode uses only components already available in the scanner loop
    (no extra DB queries per symbol). Full mode loads MTF, volume, and S/R data.
    """

    def quick_score(
        self,
        symbol: str,
        strategy_id: Optional[int],
        confidence: float,
        historical_win_rate: Optional[float],
        regime: str,
        regime_strategy_win_rate: Optional[float],
    ) -> OpportunityScore:
        parts: dict[str, Optional[float]] = {
            "historical_win_rate": historical_win_rate,
            "strategy_confidence": min(1.0, max(0.0, confidence)),
            "regime_alignment":    _REGIME_BUY_SCORE.get(regime, 0.5),
            "regime_strategy":     regime_strategy_win_rate,
        }
        return self._compute(symbol, strategy_id, parts)

    def full_score(
        self,
        symbol: str,
        strategy_id: Optional[int],
        confidence: float,
        historical_win_rate: Optional[float],
        regime: str,
        regime_strategy_win_rate: Optional[float],
        mtf_alignment: Optional[float],
        volume_score: Optional[float],
        sr_score: Optional[float],
        false_signal_rate: Optional[float] = None,
        ml_probability: Optional[float] = None,
        sector_health_score: Optional[float] = None,   # 0–1; None = unknown sector (treated as 0.5)
        confluence_count: int = 1,
    ) -> OpportunityScore:
        parts: dict[str, Optional[float]] = {
            "historical_win_rate": historical_win_rate,
            "strategy_confidence": min(1.0, max(0.0, confidence)),
            "regime_alignment":    _REGIME_BUY_SCORE.get(regime, 0.5),
            "regime_strategy":     regime_strategy_win_rate,
            "mtf_alignment":       mtf_alignment,
            "volume":              volume_score,
            "sr_context":          sr_score,
            "ml_signal_probability": ml_probability,
            "sector_health":       sector_health_score if sector_health_score is not None else 0.5,
        }
        opp = self._compute(symbol, strategy_id, parts)

        # Apply false-signal penalty as a multiplier on the base score.
        # false_signal_rate > 0.70 → 40% penalty; 0.50–0.70 → 20% penalty.
        if false_signal_rate is not None:
            rate = max(0.0, min(1.0, false_signal_rate))
            if rate >= 0.70:
                multiplier = 0.60
            elif rate >= 0.50:
                multiplier = 0.80
            else:
                multiplier = 1.0
            opp.score = round(opp.score * multiplier)
            opp.grade = _grade(opp.score)
            opp.breakdown["false_signal_rate"] = round(rate, 4)

        # Apply confluence bonus: multiple strategies agreeing boosts confidence.
        if confluence_count >= 4:
            conf_multiplier = 1.15
        elif confluence_count == 3:
            conf_multiplier = 1.10
        elif confluence_count == 2:
            conf_multiplier = 1.05
        else:
            conf_multiplier = 1.0
        if conf_multiplier != 1.0:
            opp.score = min(100, round(opp.score * conf_multiplier))
            opp.grade = _grade(opp.score)
        opp.breakdown["confluence_count"] = confluence_count

        return opp

    def _compute(
        self,
        symbol: str,
        strategy_id: Optional[int],
        parts: dict[str, Optional[float]],
    ) -> OpportunityScore:
        total_weight = 0.0
        weighted_sum = 0.0
        breakdown: dict[str, float] = {}

        for key, weight in _WEIGHTS.items():
            value = parts.get(key)
            if value is None:
                continue
            value = max(0.0, min(1.0, value))
            breakdown[key] = round(value, 4)
            weighted_sum  += value * weight
            total_weight  += weight

        raw   = weighted_sum / total_weight if total_weight > 0 else 0.5
        score = round(raw * 100)
        return OpportunityScore(
            symbol=symbol,
            strategy_id=strategy_id,
            score=score,
            grade=_grade(score),
            breakdown=breakdown,
        )
