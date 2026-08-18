# backend/domains/combinations/explanations.py
from dataclasses import dataclass


@dataclass
class CombinationExplanation:
    what_each_captures: list[str]   # one-liner per strategy
    why_complementary: str          # why these strategies work together
    typical_stocks: str             # what types of stocks this combo identifies
    works_well_in: str              # favourable market conditions
    struggles_in: str               # unfavourable market conditions
    risks_and_weaknesses: str       # known failure modes


class ExplanationGenerator:
    def explain(
        self,
        combination: list,
        result,
        correlation_matrix: dict,
    ) -> CombinationExplanation:
        """Generate structured explanation for a combination.

        Args:
            combination: list of BaseStrategy objects
            result: object with regime_win_rates dict and wf_consistency_score float
            correlation_matrix: dict mapping (name_a, name_b) tuple → correlation float (0-1)
                                 where keys are sorted tuples, e.g. ("MACD", "RSI")
        """
        what_each = [
            f"{s.name}: {s.description}" for s in combination
        ]

        why = self._why_complementary(combination, correlation_matrix)
        typical = self._typical_stocks(combination)
        works_well, struggles = self._regime_fit(result)
        risks = self._risks(result)

        return CombinationExplanation(
            what_each_captures=what_each,
            why_complementary=why,
            typical_stocks=typical,
            works_well_in=works_well,
            struggles_in=struggles,
            risks_and_weaknesses=risks,
        )

    def _why_complementary(self, combination: list, correlation_matrix: dict) -> str:
        if len(combination) < 2:
            return "Single strategy — no complementarity to analyse."

        pairs = []
        for i, s1 in enumerate(combination):
            for s2 in combination[i + 1:]:
                key = tuple(sorted([s1.name, s2.name]))
                pairs.append(correlation_matrix.get(key, 0.5))

        avg_corr = sum(pairs) / len(pairs) if pairs else 0.5

        if avg_corr < 0.3:
            return (
                f"Low average signal overlap ({avg_corr:.2f}) — each strategy captures "
                "different market dimensions and adds independent signal value."
            )
        elif avg_corr < 0.6:
            return (
                f"Moderate signal overlap ({avg_corr:.2f}) — strategies are related but "
                "partially complementary."
            )
        else:
            return (
                f"High signal overlap ({avg_corr:.2f}) — strategies tend to fire "
                "simultaneously, reducing diversification benefit."
            )

    def _typical_stocks(self, combination: list) -> str:
        types = {s.strategy_type.value for s in combination}
        if "technical" in types and "fundamental" in types:
            return "Quality stocks at technical breakout points with strong fundamental backing."
        elif "fundamental" in types:
            return "Fundamentally undervalued or high-quality stocks."
        elif "ml" in types:
            return "Stocks with historically predictable signal outcomes."
        else:
            return "Momentum and trend-following opportunities across liquid large-cap stocks."

    def _regime_fit(self, result) -> tuple[str, str]:
        regime_win_rates = getattr(result, "regime_win_rates", {})
        if not regime_win_rates:
            return "Trending markets", "Low-volume, sideways markets"

        valid = {k: v for k, v in regime_win_rates.items() if v is not None}
        if not valid:
            return "Trending markets", "Low-volume, sideways markets"

        best = max(valid, key=lambda k: valid[k])
        worst = min(valid, key=lambda k: valid[k])

        return (
            f"{best.title().replace('_', ' ')} markets ({valid[best] * 100:.0f}% win rate)",
            f"{worst.title().replace('_', ' ')} markets ({valid[worst] * 100:.0f}% win rate)",
        )

    def _risks(self, result) -> str:
        wf_consistency = getattr(result, "wf_consistency_score", None)
        if wf_consistency is None:
            return "Walk-forward consistency unknown — validate before live trading."
        if wf_consistency < 0.50:
            return (
                f"Low walk-forward consistency ({wf_consistency * 100:.0f}%) — "
                "performance may not persist out of sample."
            )
        return (
            f"Walk-forward consistency {wf_consistency * 100:.0f}%. "
            "Risk of overfitting if deployed without periodic revalidation."
        )
