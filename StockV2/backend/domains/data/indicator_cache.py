"""
Persistent per-symbol indicator cache backed by `stock_indicators_daily`.

IndicatorCache.get(symbol, prices_df):
  - If cached and current (max cached date >= latest price date): load from DB.
  - Otherwise: compute via IndicatorEngine, persist new rows, return DataFrame.

The returned DataFrame matches IndicatorEngine.compute() output exactly —
pass it as _df_ind_precomputed to BacktestSimulator.run() for zero recomputation.
"""
import logging

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from domains.data.indicators import IndicatorEngine

logger = logging.getLogger(__name__)

# All indicator columns stored in stock_indicators_daily
IND_COLS: list[str] = [
    "open", "high", "low", "close", "volume",
    "sma_5", "sma_10", "sma_20", "sma_50",
    "ema_5", "ema_7", "ema_9", "ema_10", "ema_13", "ema_14", "ema_21", "ema_22", "ema_26", "ema_50",
    "zlema_14",
    "rsi_5", "rsi_9", "rsi_14",
    "macd", "macd_signal", "macd_hist",
    "bb_upper", "bb_middle", "bb_lower", "bb_width", "bb_width_sma_20",
    "atr_14", "atr_ratio", "atr_5bar_change",
    "adx_14", "dmi_plus_14", "dmi_minus_14",
    "supertrend", "supertrend_direction",
    "psar", "psar_bull",
    "vortex_pos", "vortex_neg",
    "fisher_9",
    "donchian_high_20", "donchian_low_20", "donchian_mid_20",
    "stoch_k", "stoch_d", "stoch_rsi_k", "stoch_rsi_d",
    "cmf_20",
    "mfi_14", "cci_20", "williams_r", "roc_10",
    "ichimoku_tenkan", "ichimoku_kijun", "ichimoku_span_a", "ichimoku_span_b",
    "ichimoku_cloud_a", "ichimoku_cloud_b",
    "chandelier_long",
    "ao", "alligator_jaw", "alligator_teeth", "alligator_lips",
    "rolling_high_200",
    "volume_sma_20", "volume_ratio", "volume_sma_5bar_change",
    "obv", "obv_sma_10",
    "gap_pct",
    # Strategy-specific precomputed (eliminates O(n²)/GIL-serialised work)
    "sma_200",
    "hma_50", "ut_bot_stop",
    "squeeze_on", "squeeze_mom",
    "qqe_fast_rsi", "qqe_fast", "qqe_slow_rsi", "qqe_slow",
    "connors_rsi",
    "lorentzian_pred",
    "nw_yhat", "nw_upper", "nw_lower",
    "mc_wt1", "mc_wt2", "rsimfi_60",
]

_SEL = f"SELECT date, {', '.join(IND_COLS)} FROM stock_indicators_daily WHERE symbol = :s ORDER BY date ASC"
_INS = (
    f"INSERT OR IGNORE INTO stock_indicators_daily (symbol, date, {', '.join(IND_COLS)}) "
    f"VALUES (:sym, :d, {', '.join(f':{c}' for c in IND_COLS)})"
)


class IndicatorCache:
    def __init__(self, db: Session):
        self.db = db

    def get(self, symbol: str, prices_df: pd.DataFrame) -> pd.DataFrame:
        """Return full indicator DataFrame. Computes+stores if stale, loads from DB if current."""
        latest_date = str(prices_df["date"].max())
        cached_max = self.db.execute(
            text("SELECT MAX(date) FROM stock_indicators_daily WHERE symbol = :s"),
            {"s": symbol},
        ).scalar()

        if cached_max is not None and str(cached_max) >= latest_date:
            return self._load(symbol)

        df_ind = IndicatorEngine.compute(prices_df)
        self._store(symbol, df_ind, cached_max)
        return df_ind

    # ── private ──────────────────────────────────────────────────────────────

    def _load(self, symbol: str) -> pd.DataFrame:
        rows = self.db.execute(text(_SEL), {"s": symbol}).fetchall()
        df = pd.DataFrame([dict(r._mapping) for r in rows])
        df["date"] = pd.to_datetime(df["date"]).dt.date
        # SQLite NULLs arrive as Python None → object dtype columns.
        # Convert every indicator column to float so strategies get NaN (not None),
        # which their pd.isna() guards handle correctly.
        for col in IND_COLS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    def _store(self, symbol: str, df_ind: pd.DataFrame, cached_max) -> None:
        # Only write rows newer than what's already cached
        if cached_max is not None:
            df_new = df_ind[df_ind["date"].astype(str) > str(cached_max)]
        else:
            df_new = df_ind

        if df_new.empty:
            return

        # Build the column presence map once (some indicators may be absent on tiny history)
        col_present = {col: col in df_new.columns for col in IND_COLS}

        batch: list[dict] = []
        for row in df_new.itertuples(index=False):
            d = str(getattr(row, "date"))
            entry: dict = {"sym": symbol, "d": d}
            for col in IND_COLS:
                if not col_present[col]:
                    entry[col] = None
                    continue
                v = getattr(row, col, None)
                if v is None:
                    entry[col] = None
                else:
                    try:
                        f = float(v)
                        entry[col] = None if np.isnan(f) else f
                    except (TypeError, ValueError):
                        entry[col] = None
            batch.append(entry)

        if not batch:
            return

        self.db.execute(text(_INS), batch)
        self.db.commit()
        logger.info("[IndicatorCache] %s: stored %d rows", symbol, len(batch))
