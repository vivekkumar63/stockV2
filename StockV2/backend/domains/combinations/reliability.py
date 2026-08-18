# backend/domains/combinations/reliability.py
from dataclasses import dataclass
from typing import Optional

from domains.combinations.metrics import ExtendedMetrics


@dataclass
class ReliabilityResult:
    score: float             # 0.0–100.0 (Pass 1 formula, unchanged by Pass 2)
    label: str               # "Strong evidence" | "Moderate evidence" | "Weak evidence" | "Likely Overfitted" | "Insufficient Data"
    component_scores: dict   # breakdown: 6 keys summing to total_score
    evidence_summary: str    # 1–2 sentence explanation


class ReliabilityScorer:
    def score(
        self,
        train: ExtendedMetrics,
        val: ExtendedMetrics,
        oos: ExtendedMetrics,
        wf_consistency: float,
    ) -> ReliabilityResult:
        """Pass 1: 6-component scoring without sensitivity.

        Components and weights:
        - OOS performance   30%  min(1, max(0, oos_cagr / 20.0)) * 30
        - WF consistency    25%  wf_consistency * 25
        - Train→OOS gap     20%  (1 - degradation) * 20   where degradation = (train_cagr - oos_cagr) / train_cagr
        - Drawdown control  10%  (1 - min(1, abs(oos_dd) / 50.0)) * 10
        - Signal sufficiency 10% min(1, oos_trades / 50) * 10
        - Regime coverage    5%  (positive_regime_count / 3) * 5

        Returns ReliabilityResult with score, label, component breakdown, and evidence summary.
        """
        oos_cagr = oos.cagr or 0.0
        train_cagr = train.cagr or 0.0

        # Component 1: OOS performance (30%)
        oos_perf_score = min(1.0, max(0.0, oos_cagr / 20.0)) * 30.0

        # Component 2: Walk-forward consistency (25%)
        wf_score = min(1.0, max(0.0, wf_consistency)) * 25.0

        # Component 3: Train→OOS degradation (20%)
        if train_cagr > 0:
            degradation = (train_cagr - oos_cagr) / train_cagr
        else:
            degradation = 1.0
        degradation_score = (1.0 - min(1.0, max(0.0, degradation))) * 20.0

        # Component 4: Drawdown control (10%)
        oos_dd = abs(oos.max_drawdown or 0.0)
        dd_score = (1.0 - min(1.0, oos_dd / 50.0)) * 10.0

        # Component 5: Signal sufficiency (10%)
        signal_score = min(1.0, oos.total_trades / 50.0) * 10.0

        # Component 6: Regime coverage (5%)
        positive_regimes = sum(
            1 for wr in oos.regime_win_rates.values()
            if wr is not None and wr > 0
        )
        regime_score = (min(positive_regimes, 3) / 3.0) * 5.0

        total_score = round(
            oos_perf_score + wf_score + degradation_score
            + dd_score + signal_score + regime_score,
            2,
        )

        # Label assignment
        if oos.total_trades < 20:
            label = "Insufficient Data"
        elif total_score >= 75:
            label = "Strong evidence"
        elif total_score >= 55:
            label = "Moderate evidence"
        elif total_score >= 40:
            label = "Weak evidence"
        elif degradation > 0.60 or total_score >= 25:
            label = "Likely Overfitted"
        else:
            label = "Insufficient Data"

        component_scores = {
            "oos_performance": round(oos_perf_score, 2),
            "wf_consistency": round(wf_score, 2),
            "train_oos_stability": round(degradation_score, 2),
            "drawdown_control": round(dd_score, 2),
            "signal_sufficiency": round(signal_score, 2),
            "regime_coverage": round(regime_score, 2),
        }

        evidence = _build_evidence_summary(label, total_score, oos, wf_consistency)

        return ReliabilityResult(
            score=total_score,
            label=label,
            component_scores=component_scores,
            evidence_summary=evidence,
        )

    def apply_sensitivity_cap(
        self,
        result: ReliabilityResult,
        sensitivity_score: float,
    ) -> ReliabilityResult:
        """Pass 2: cap label if sensitivity is poor. Score value is unchanged.

        Rules:
        - sensitivity_score < 40 AND label is "Strong evidence" → downgrade to "Moderate evidence"
        - sensitivity_score < 20 AND label in ("Strong evidence", "Moderate evidence") → downgrade to "Weak evidence"
        """
        new_label = result.label

        if sensitivity_score < 20 and result.label in ("Strong evidence", "Moderate evidence"):
            new_label = "Weak evidence"
        elif sensitivity_score < 40 and result.label == "Strong evidence":
            new_label = "Moderate evidence"

        return ReliabilityResult(
            score=result.score,
            label=new_label,
            component_scores=result.component_scores,
            evidence_summary=result.evidence_summary,
        )


def _build_evidence_summary(
    label: str,
    score: float,
    oos: ExtendedMetrics,
    wf_consistency: float,
) -> str:
    oos_cagr = oos.cagr or 0.0
    trades = oos.total_trades
    if label == "Strong evidence":
        return (
            f"High reliability (score={score:.0f}): OOS CAGR {oos_cagr:.1f}%, "
            f"WF consistency {wf_consistency * 100:.0f}%, {trades} signals."
        )
    elif label == "Moderate evidence":
        return f"Moderate reliability (score={score:.0f}): some OOS evidence, acceptable consistency."
    elif label == "Weak evidence":
        return f"Weak reliability (score={score:.0f}): limited OOS evidence or low walk-forward consistency."
    elif label == "Likely Overfitted":
        return f"Likely overfitted (score={score:.0f}): large train→OOS gap or poor walk-forward consistency."
    else:
        return f"Insufficient data (score={score:.0f}): too few OOS signals ({trades}) for confidence."
