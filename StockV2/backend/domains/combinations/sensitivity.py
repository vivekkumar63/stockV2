# backend/domains/combinations/sensitivity.py
import logging
import statistics
from datetime import date

import pandas as pd


logger = logging.getLogger(__name__)


class SensitivityAnalyzer:
    def test(
        self,
        combination: list,
        prices_df_map: dict[str, pd.DataFrame],
        from_date: date,
        to_date: date,
        base_threshold: float = 0.65,
        df_ind_map: dict[str, pd.DataFrame] | None = None,
    ) -> float:
        """Test stability of a combination across 5 consensus threshold variations.

        Returns sensitivity score 0-100 where higher = more stable.
        df_ind_map: pre-loaded indicator DataFrames (pass from engine to avoid recompute).
        """
        variations = [0.80, 0.90, 1.00, 1.10, 1.20]
        thresholds = [base_threshold * v for v in variations]

        buy_counts: list[int] = []

        for threshold in thresholds:
            total_buys = self._count_buy_signals(
                combination, prices_df_map, from_date, to_date, threshold, df_ind_map
            )
            buy_counts.append(total_buys)

        if not buy_counts or all(c == 0 for c in buy_counts):
            return 0.0

        mean_count = statistics.mean(buy_counts)
        std_count = statistics.stdev(buy_counts) if len(buy_counts) > 1 else 0.0
        cv = std_count / mean_count  # coefficient of variation

        sensitivity = max(0.0, 1.0 - cv)
        return round(sensitivity * 100.0, 2)

    def _count_buy_signals(
        self,
        combination: list,
        prices_df_map: dict[str, pd.DataFrame],
        from_date: date,
        to_date: date,
        threshold: float,
        df_ind_map: dict[str, pd.DataFrame] | None = None,
    ) -> int:
        """Count how many BUY signals the combination generates at a given threshold."""
        total_buys = 0
        min_required = max(2, len(combination) // 2 + 1)  # majority vote

        for symbol, prices_df in prices_df_map.items():
            # Filter to the date range
            mask = (prices_df["date"] >= from_date) & (prices_df["date"] <= to_date)
            df_range = prices_df[mask].reset_index(drop=True)
            if df_range.empty or len(df_range) < 20:
                continue

            try:
                if df_ind_map is None or symbol not in df_ind_map:
                    continue  # skip if no indicators — engine always passes them in
                df_ind = df_ind_map[symbol]
                df_ind_range = df_ind[df_ind["date"] >= from_date].reset_index(drop=True)
            except Exception:
                continue

            if df_ind_range.empty:
                continue

            # For each date in range, apply all strategies and count days with consensus BUY
            for _, row in df_ind_range.iterrows():
                row_df = df_ind_range[df_ind_range["date"] <= row["date"]].tail(50)
                if len(row_df) < 2:
                    continue

                buy_count = 0
                total_confidence = 0.0
                for strategy in combination:
                    try:
                        signal = strategy.generate_signal(row_df)
                        if signal.signal_type == "BUY":
                            buy_count += 1
                            total_confidence += signal.confidence
                    except Exception:
                        continue

                if buy_count == 0:
                    continue
                avg_confidence = total_confidence / buy_count
                # Consensus: avg confidence above threshold AND enough strategies agree
                if avg_confidence >= threshold and buy_count >= min_required:
                    total_buys += 1

        return total_buys
