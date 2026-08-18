# backend/domains/combinations/search.py
import logging
from dataclasses import dataclass
from itertools import combinations
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class SearchConfig:
    max_pairs_exhaustive: int = 435     # C(30,2) — always exhaustive
    top_pairs_for_triplets: int = 50    # extend these with greedy
    top_triplets_for_quads: int = 20
    max_size: int = 5


class ComboSearch:
    def __init__(self, candidates: list, config: SearchConfig | None = None):
        self.candidates = candidates
        self.config = config if config is not None else SearchConfig()

    def generate_combinations(self) -> list[list]:
        """Return all pairs as exhaustive list of 2-strategy lists.

        Pairs are deduplicated: (A, B) and (B, A) are the same combination.
        The canonical form is sorted by strategy name.
        """
        seen: set[tuple[str, ...]] = set()
        combos: list[list] = []

        for combo in combinations(self.candidates, 2):
            key = tuple(sorted(s.name for s in combo))
            if key in seen:
                continue
            seen.add(key)
            combos.append(list(combo))

        logger.info("[search] generated %d pairs from %d candidates", len(combos), len(self.candidates))
        return combos

    def greedy_extend(
        self,
        base: list,
        remaining: list,
        score_fn: Callable[[list], float],
    ) -> list:
        """Add the single strategy from remaining that maximises score_fn(extended_combo).

        If no strategy improves the score, returns base unchanged.
        """
        best_strategy = None
        best_score = score_fn(base)

        for candidate in remaining:
            if any(candidate.name == s.name for s in base):
                continue  # already in base
            extended = base + [candidate]
            score = score_fn(extended)
            if score > best_score:
                best_score = score
                best_strategy = candidate

        if best_strategy:
            return base + [best_strategy]
        return base
