# Strategy Combination Engine — Design Spec

**Goal:** Discover which combinations of the existing 92 strategies work best together using statistically rigorous methodology — prioritising robustness, consistency, and out-of-sample reliability over raw historical returns.

**Architecture:** A new `domains/combinations/` backend domain with five focused units (filter, search, metrics, reliability, sensitivity) orchestrated by a `CombinationEngine`. Results are persisted to four new DB tables and exposed via eight REST endpoints. A scheduled weekly job runs the full pipeline; a manual trigger endpoint allows on-demand reruns. A new `CombinationsPage` frontend page consumes all endpoints and displays ranked combinations, drill-down detail, and benchmark comparisons.

**Tech Stack:** Python + SQLAlchemy + FastAPI (backend), React + TanStack Query v5 + Tailwind CSS (frontend), APScheduler (scheduling). Reuses existing `BacktestSimulator`, `WalkForward`, `compute_metrics`, `SignalAggregator`, `IndicatorEngine` unchanged.

---

## Search Space & Anti-Overfitting Strategy

With 92 strategies the raw combination space is unworkable (C(92,5) ≈ 55M). The engine uses a two-stage approach:

**Stage 1 — Pre-filter to candidates (92 → top-30 overall + top-15 per regime)**
- Config floor: min 30 trades, max drawdown ≤ 40%, win rate ≥ 35%
- Multi-factor score = `0.30×Sharpe + 0.30×walk_forward_consistency + 0.20×win_rate + 0.20×profit_factor`
- Top-30 by multi-factor score = overall candidate pool
- Regime-specific pools: top-15 per regime (BULL / SIDEWAYS / BEAR) independently

**Stage 2 — Greedy forward selection**
- Pairs: exhaustive C(30,2) = 435 combinations (feasible)
- Triplets: greedy — start with top-50 pairs, add the single strategy that maximally improves the multi-factor score on the validation set
- Quadruplets: greedy — extend top-20 triplets
- Max combination size: 5 (diminishing signal count + explainability degrades beyond this)

**Time split (anti-overfitting):**
- First 60% of each symbol's history = **training set** (strategy selection and scoring)
- Middle 20% = **validation set** (greedy forward search decisions)
- Final 20% = **out-of-sample (OOS) test** (never touched during selection — honest evaluation only)
- Walk-forward: 12-month train / 3-month test windows rolled across full history (provides consistency scores)

---

## Backend

### File Map

| File | Action | Purpose |
|---|---|---|
| `backend/domains/combinations/__init__.py` | Create | Package |
| `backend/domains/combinations/engine.py` | Create | `CombinationEngine` — full pipeline orchestrator |
| `backend/domains/combinations/filter.py` | Create | `StrategyFilter` — 92 → top-30 candidates |
| `backend/domains/combinations/search.py` | Create | `ComboSearch` — exhaustive pairs + greedy forward |
| `backend/domains/combinations/metrics.py` | Create | `CombinationMetrics` — extended metrics + benchmarks |
| `backend/domains/combinations/reliability.py` | Create | `ReliabilityScorer` — 0–100 score + confidence label |
| `backend/domains/combinations/sensitivity.py` | Create | `SensitivityAnalyzer` — consensus threshold perturbation |
| `backend/domains/combinations/explanations.py` | Create | `ExplanationGenerator` — WHY text for top combinations |
| `backend/domains/combinations/router.py` | Create | FastAPI router with 8 endpoints |
| `backend/main.py` | Modify | Register `/combinations` router + DB migration |
| `backend/scheduler.py` | Modify | Add weekly combination analysis job |
| `backend/tests/test_combination_engine.py` | Create | Unit + integration tests |

---

### Database Schema

#### `strategy_combinations` table

```sql
CREATE TABLE IF NOT EXISTS strategy_combinations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,              -- e.g. "RSI_MACD_SuperTrend"
    strategy_ids    TEXT NOT NULL,              -- JSON array of strategy DB IDs
    strategy_names  TEXT NOT NULL,              -- JSON array of strategy names
    size            INTEGER NOT NULL,           -- 2, 3, 4, or 5
    search_method   TEXT NOT NULL,              -- "exhaustive" | "greedy"
    created_at      DATETIME DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_combination_ids ON strategy_combinations(strategy_ids);
```

#### `combination_results` table

```sql
CREATE TABLE IF NOT EXISTS combination_results (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    combination_id          INTEGER NOT NULL REFERENCES strategy_combinations(id),
    run_id                  INTEGER NOT NULL REFERENCES combination_run_log(id),

    -- Training period metrics
    train_cagr              REAL,
    train_sharpe            REAL,
    train_win_rate          REAL,
    train_max_drawdown      REAL,
    train_profit_factor     REAL,
    train_total_trades      INTEGER,
    train_sortino           REAL,

    -- Validation period metrics
    val_cagr                REAL,
    val_sharpe              REAL,
    val_win_rate            REAL,
    val_max_drawdown        REAL,
    val_total_trades        INTEGER,

    -- Out-of-sample metrics
    oos_cagr                REAL,
    oos_sharpe              REAL,
    oos_win_rate            REAL,
    oos_max_drawdown        REAL,
    oos_profit_factor       REAL,
    oos_total_trades        INTEGER,
    oos_sortino             REAL,
    oos_median_return_pct   REAL,

    -- Walk-forward summary
    wf_consistency_score    REAL,               -- fraction of windows with win_rate >= 40%
    wf_avg_oos_cagr         REAL,

    -- Benchmark deltas (OOS period)
    vs_buy_and_hold_cagr    REAL,               -- oos_cagr - bah_cagr
    vs_best_single_cagr     REAL,               -- oos_cagr - best_individual_strategy_cagr
    vs_sma_crossover_cagr   REAL,

    -- Reliability scoring
    reliability_score       REAL,               -- 0.0–100.0
    reliability_label       TEXT,               -- "Strong" | "Moderate" | "Weak" | "Likely Overfitted" | "Insufficient Data"
    sensitivity_score       REAL,               -- 0.0–100.0 (parameter stability)

    -- Explanation
    explanation_json        TEXT,               -- JSON with why_text, regime_fit, weaknesses

    computed_at             DATETIME DEFAULT (datetime('now'))
);
```

#### `combination_regime_perf` table

```sql
CREATE TABLE IF NOT EXISTS combination_regime_perf (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    combination_id  INTEGER NOT NULL REFERENCES strategy_combinations(id),
    run_id          INTEGER NOT NULL REFERENCES combination_run_log(id),
    regime          TEXT NOT NULL,              -- BULL | SIDEWAYS | BEAR | STRONG_BULL | STRONG_BEAR
    win_rate        REAL,
    avg_pnl_pct     REAL,
    trade_count     INTEGER,
    cagr            REAL
);
```

#### `combination_run_log` table

```sql
CREATE TABLE IF NOT EXISTS combination_run_log (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at              DATETIME NOT NULL,
    completed_at            DATETIME,
    status                  TEXT NOT NULL DEFAULT 'running',  -- "running" | "complete" | "failed"
    symbols_analyzed        INTEGER,
    candidates_selected     INTEGER,
    combinations_tested     INTEGER,
    top_combination_id      INTEGER REFERENCES strategy_combinations(id),
    error_message           TEXT,
    config_json             TEXT                -- JSON snapshot of config used
);
```

---

### Component Specifications

#### `StrategyFilter` (`filter.py`)

```python
@dataclass
class FilterConfig:
    min_trades: int = 30
    max_drawdown: float = 0.40
    min_win_rate: float = 0.35
    top_n_overall: int = 30
    top_n_per_regime: int = 15
    sharpe_weight: float = 0.30
    wf_consistency_weight: float = 0.30
    win_rate_weight: float = 0.20
    profit_factor_weight: float = 0.20

class StrategyFilter:
    def __init__(self, db: Session, config: FilterConfig = FilterConfig()): ...

    def select_candidates(self) -> dict:
        """
        Returns:
        {
            "overall": list[BaseStrategy],          # top_n_overall strategies
            "by_regime": {
                "BULL": list[BaseStrategy],          # top_n_per_regime
                "SIDEWAYS": list[BaseStrategy],
                "BEAR": list[BaseStrategy],
            },
            "scores": dict[str, float],             # strategy_name -> multi_factor_score
            "disqualified": list[str],              # strategy names that failed config floor
        }
        """
```

Multi-factor score reads from `strategy_performance` (pre-computed individual backtests) and `walk_forward_results` (consistency scores). Strategies absent from either table are disqualified with reason logged.

---

#### `ComboSearch` (`search.py`)

```python
@dataclass
class SearchConfig:
    max_pairs_exhaustive: int = 435         # C(30,2) — always exhaustive
    top_pairs_for_triplets: int = 50        # extend these with greedy
    top_triplets_for_quads: int = 20
    max_size: int = 5

class ComboSearch:
    def __init__(self, candidates: list[BaseStrategy], config: SearchConfig = SearchConfig()): ...

    def generate_combinations(self) -> list[list[BaseStrategy]]:
        """Returns all combinations to test, sorted by size."""

    def greedy_extend(
        self,
        base: list[BaseStrategy],
        remaining: list[BaseStrategy],
        score_fn: Callable[[list[BaseStrategy]], float],
    ) -> list[BaseStrategy]:
        """Add the single strategy from remaining that maximises score_fn on validation set."""
```

Combination de-duplication: strategy_ids sorted before hashing to avoid (A,B) and (B,A) being counted as different.

---

#### `CombinationMetrics` (`metrics.py`)

Extends existing `compute_metrics()` with:

```python
@dataclass
class ExtendedMetrics:
    # All fields from existing compute_metrics() dict
    total_trades: int
    win_rate: float
    total_pnl: float
    total_return_pct: float
    cagr: float
    sharpe_ratio: float
    max_drawdown: float
    profit_factor: float
    avg_return_pct: float
    # New fields
    sortino_ratio: float        # uses only downside deviation
    median_return_pct: float    # median trade return (less sensitive to outliers)
    regime_win_rates: dict      # {regime_label: win_rate} from market_regime join
    benchmark_deltas: dict      # {bah: float, best_single: float, sma_cross: float}

def compute_extended_metrics(
    trades: list[SimTrade],
    initial_capital: float,
    from_date: date,
    to_date: date,
    db: Session,
    benchmarks: dict,
) -> ExtendedMetrics: ...
```

Benchmark computation:
- **Buy-and-hold**: Equal-weight buy of all symbols at `from_date` close, sell at `to_date` close. Uses `stock_prices_daily`. Returns average CAGR across all symbols.
- **Best single strategy**: Max OOS CAGR among the filtered candidates.
- **SMA crossover**: Fixed rule — buy when SMA20 crosses above SMA50, sell on cross below. Computed once per run and cached.

---

#### `ReliabilityScorer` (`reliability.py`)

**Two-pass scoring process** (resolves circular dependency with sensitivity):

- **Pass 1 (all combinations):** Score using the 5-component formula below → select top-30 by score
- **Pass 2 (top-30 only):** Run `SensitivityAnalyzer`, then apply sensitivity as a label cap on the Pass 1 result

```python
@dataclass
class ReliabilityResult:
    score: float                # 0.0–100.0 (Pass 1 formula)
    label: str                  # "Strong" | "Moderate" | "Weak" | "Likely Overfitted" | "Insufficient Data"
    component_scores: dict      # breakdown per component (5 keys)
    evidence_summary: str       # 1–2 sentence explanation of the label

class ReliabilityScorer:
    def score(
        self,
        train: ExtendedMetrics,
        val: ExtendedMetrics,
        oos: ExtendedMetrics,
        wf_consistency: float,
    ) -> ReliabilityResult:
        """Pass 1: score without sensitivity. Used for all 435+ combinations."""

    def apply_sensitivity_cap(
        self,
        result: ReliabilityResult,
        sensitivity_score: float,
    ) -> ReliabilityResult:
        """Pass 2: cap the label if sensitivity is poor.
        If sensitivity_score < 40 and label is "Strong", downgrade to "Moderate".
        If sensitivity_score < 20, downgrade any label to "Weak" or below.
        Score value is unchanged — only the label is capped.
        """
```

**Pass 1 Scoring formula (5 components, sum to 100%):**

| Component | Weight | Formula |
|---|---|---|
| OOS performance | 30% | `min(1, max(0, oos_cagr / 0.20))` — 20% CAGR = full score |
| Walk-forward consistency | 25% | `wf_consistency` (already in 0–1) |
| Train→OOS degradation | 20% | `1 - clamp((train_cagr - oos_cagr) / train_cagr, 0, 1)` |
| Drawdown control | 10% | `1 - clamp(oos_max_drawdown / 0.50, 0, 1)` |
| Signal sufficiency | 10% | `min(1, oos_total_trades / 50)` |
| Regime coverage | 5% | `positive_regime_count / 3` |

**Label assignment (after Pass 1, before sensitivity cap):**
- Score 75–100: **Strong evidence**
- Score 55–74: **Moderate evidence**
- Score 40–54: **Weak evidence**
- Score 25–39 OR `(train_cagr - oos_cagr) / train_cagr > 0.60`: **Likely Overfitted**
- Score 0–24 OR `oos_total_trades < 20`: **Insufficient Data**

**Pass 2 sensitivity label cap:**
- `sensitivity_score < 40` AND current label is "Strong evidence" → downgrade to "Moderate evidence"
- `sensitivity_score < 20` → downgrade to "Weak evidence" minimum (regardless of score)

---

#### `SensitivityAnalyzer` (`sensitivity.py`)

Tests stability of a combination by varying the consensus threshold used by `SignalAggregator`:

```python
class SensitivityAnalyzer:
    def test(
        self,
        combination: list[BaseStrategy],
        prices_df_map: dict[str, pd.DataFrame],
        from_date: date,
        to_date: date,
        base_threshold: float = 0.65,
    ) -> float:
        """
        Runs backtest at threshold variations: ±10%, ±20% of base_threshold.
        Sensitivity score = 1 - (std of CAGR across variations / mean of CAGR across variations).
        Returns 0.0–1.0, scaled to 0–100 in ReliabilityScorer.
        A score of 80+ means performance is stable across parameter changes.
        """
```

Run only on top-30 combinations after initial ranking (too expensive for all 435+ combinations).

---

#### `ExplanationGenerator` (`explanations.py`)

Generates structured explanation for each top combination:

```python
@dataclass
class CombinationExplanation:
    what_each_captures: list[str]   # per-strategy one-liner
    why_complementary: str          # why these strategies work together
    typical_stocks: str             # what types of stocks the combo identifies
    works_well_in: str              # market conditions favourable
    struggles_in: str               # market conditions unfavourable
    risks_and_weaknesses: str       # known failure modes

class ExplanationGenerator:
    def explain(
        self,
        combination: list[BaseStrategy],
        result: CombinationResults,
        correlation_matrix: dict,       # from strategy_correlations table
    ) -> CombinationExplanation: ...
```

Explanation logic uses:
- Strategy `description` field (already set on every `BaseStrategy` subclass)
- `strategy_correlations` table values: if two strategies have correlation < 0.3, they are "complementary" (capture different signals)
- Regime performance breakdown: identifies which regimes the combo excels in
- Strategy type mix: technical momentum + fundamental value = "quality growth at breakout"
- Walk-forward window analysis: if consistency drops in BEAR windows, note this as a weakness

---

#### `CombinationEngine` (`engine.py`)

```python
@dataclass
class EngineConfig:
    filter: FilterConfig = FilterConfig()
    search: SearchConfig = SearchConfig()
    symbols_limit: int = 200            # max symbols to run backtest on
    initial_capital: float = 500_000.0
    round_trip_cost_pct: float = 0.30
    train_ratio: float = 0.60
    val_ratio: float = 0.20
    # oos_ratio = 1 - train_ratio - val_ratio = 0.20
    sensitivity_top_n: int = 30         # run sensitivity only on top-N combinations
    explanation_top_n: int = 20         # generate explanations for top-N

class CombinationEngine:
    def __init__(self, db: Session, config: EngineConfig = EngineConfig()): ...

    def run_full_analysis(self) -> int:
        """
        Runs the complete pipeline. Returns the run_id.
        Steps:
          1. Create run log entry (status=running)
          2. StrategyFilter.select_candidates()
          3. ComboSearch.generate_combinations()
          4. For each combination × symbol:
               - Split prices into train/val/oos windows
               - BacktestSimulator.run() on train, val, oos periods separately
               - WalkForward across full history
          5. compute_extended_metrics() for each period
          6. ReliabilityScorer.score() Pass 1 for all combinations (5-component formula)
          7. Select top-30 by Pass 1 score
          8. SensitivityAnalyzer.test() on top-30 only
          9. ReliabilityScorer.apply_sensitivity_cap() on top-30 (Pass 2 — label cap only)
         10. ExplanationGenerator.explain() on top-20
         11. Persist all results to DB
         12. Update run log (status=complete)
        """

    def get_top_combinations(self, n: int = 50) -> list[dict]: ...
    def get_best_by_category(self) -> dict: ...
    def get_combinations_to_avoid(self) -> list[dict]: ...
```

Progress logging every 10% of combinations processed.

---

### API Endpoints (`router.py`)

**File:** `backend/domains/combinations/router.py`

All endpoints are read-only except `POST /combinations/analyze`. No auth change needed (uses same `get_db` dependency pattern as existing routers).

```python
router = APIRouter(prefix="/combinations", tags=["combinations"])

GET  /combinations/rankings
    Query params: size (int, optional), regime (str, optional), sort_by (str, default="reliability_score")
    Returns: list[CombinationSummary], sorted descending

GET  /combinations/{combination_id}
    Returns: CombinationDetail (full metrics + explanation + regime perf + benchmark deltas)

GET  /combinations/best
    Returns: {
        "overall": CombinationSummary,
        "low_risk": CombinationSummary,       # lowest max_drawdown with reliability >= 55
        "high_growth": CombinationSummary,    # highest oos_cagr with reliability >= 55
        "most_consistent": CombinationSummary # highest wf_consistency_score
    }

GET  /combinations/avoid
    Returns: list[CombinationSummary] where reliability_label in ("Likely Overfitted", "Insufficient Data")

GET  /combinations/run-status
    Returns: {
        "status": "running" | "complete" | "failed" | "never_run",
        "last_completed_at": str | null,
        "last_run_id": int | null,
        "combinations_tested": int | null,
        "top_combination": CombinationSummary | null
    }

POST /combinations/analyze
    Body: { "config": EngineConfig | null }   # null = use defaults
    Returns: { "status": "started", "run_id": int }
    Fires CombinationEngine.run_full_analysis() in daemon thread
```

**Response shapes:**

```python
# CombinationSummary (used in rankings + best + avoid)
{
    "combination_id": int,
    "name": str,
    "strategies": list[str],           # strategy names
    "size": int,
    "oos_cagr": float,
    "oos_max_drawdown": float,
    "oos_sharpe": float,
    "oos_win_rate": float,
    "oos_total_trades": int,
    "train_cagr": float,
    "wf_consistency_score": float,
    "reliability_score": float,
    "reliability_label": str,
    "sensitivity_score": float,
    "vs_buy_and_hold_cagr": float,
    "vs_best_single_cagr": float,
}

# CombinationDetail (used in single-combination endpoint)
{
    **CombinationSummary,
    "val_cagr": float,
    "oos_sortino": float,
    "oos_median_return_pct": float,
    "oos_profit_factor": float,
    "regime_performance": [{"regime": str, "win_rate": float, "trade_count": int, "cagr": float}],
    "reliability_breakdown": {"oos_performance": float, "wf_consistency": float, ...},
    "explanation": {
        "what_each_captures": list[str],
        "why_complementary": str,
        "typical_stocks": str,
        "works_well_in": str,
        "struggles_in": str,
        "risks_and_weaknesses": str
    },
    "vs_sma_crossover_cagr": float,
}
```

---

### Scheduler Integration

**File:** `backend/scheduler.py` (modify)

```python
def _run_combination_analysis():
    from database import SessionLocal
    from domains.combinations.engine import CombinationEngine
    db = SessionLocal()
    try:
        engine = CombinationEngine(db)
        run_id = engine.run_full_analysis()
        logger.info("[combination_analysis] complete: run_id=%d", run_id)
    except Exception:
        logger.exception("[combination_analysis] failed")
    finally:
        db.close()

scheduler.add_job(
    _run_combination_analysis,
    CronTrigger(day_of_week="sun", hour=22, minute=0, timezone="Asia/Kolkata"),
    id="combination_analysis",
    replace_existing=True,
)
```

Runs at 10pm Sunday — 2 hours after the fundamentals refresh job.

---

### Bias Warnings

The system logs the following known biases in `combination_run_log.config_json`:

1. **Survivorship bias**: Only symbols currently in `stock_prices_daily` are tested. Delisted stocks are absent. OOS performance is likely slightly optimistic.
2. **Look-ahead bias in fundamentals**: `FundamentalsService` fetches current values, not point-in-time historical snapshots. Fundamental strategies' OOS metrics are unreliable until a time-series fundamentals store is added (deferred to a future phase).
3. **Data leakage via indicator warmup**: `IndicatorEngine` uses only past bars (no future data leakage) — this is safe.
4. **Limited OOS sample**: For symbols with only 3–4 years of history, the 20% OOS window may contain fewer than 20 trades. These combinations receive label "Insufficient Data" automatically.

---

### Testing

**File:** `backend/tests/test_combination_engine.py`

```python
# StrategyFilter tests
test_filter_disqualifies_low_trade_strategies()      # strategy with 10 trades is excluded
test_filter_computes_multifactor_score_correctly()   # verify weighted formula
test_filter_returns_top_n_overall()                  # verify exactly 30 returned (or fewer if <30 qualify)
test_filter_returns_regime_specific_pools()          # BULL pool != BEAR pool

# ComboSearch tests
test_search_generates_all_pairs_exhaustively()       # C(n,2) pairs generated
test_search_greedy_extend_picks_best_marginal()      # greedy adds highest-scoring strategy
test_search_deduplicates_reversed_pairs()            # (A,B) and (B,A) are same combination

# ReliabilityScorer tests
test_scorer_labels_strong_when_all_components_high()
test_scorer_labels_overfitted_when_train_oos_gap_large()
test_scorer_labels_insufficient_when_oos_trades_low()
test_scorer_components_sum_to_100()

# SensitivityAnalyzer tests
test_sensitivity_returns_1_when_perfectly_stable()   # identical CAGR across all threshold variations
test_sensitivity_returns_low_score_when_volatile()   # CAGR swings wildly with threshold changes

# Integration test
test_combination_engine_run_full_analysis_smoke()
    # Uses in-memory SQLite + 2 strategies + 5 symbols
    # Verifies: run_log created, combination_results populated, no exceptions
```

---

## Frontend

### File Map

| File | Action | Purpose |
|---|---|---|
| `frontend/src/pages/CombinationsPage.tsx` | Create | Main combinations page |
| `frontend/src/api/combinations.ts` | Create | API call functions |
| `frontend/src/App.tsx` | Modify | Add `/combinations` route |
| `frontend/src/components/Sidebar.tsx` | Modify | Add nav link "Strategy Combos" |

---

### `frontend/src/api/combinations.ts`

```typescript
export interface CombinationSummary {
  combination_id: number
  name: string
  strategies: string[]
  size: number
  oos_cagr: number
  oos_max_drawdown: number
  oos_sharpe: number
  oos_win_rate: number
  oos_total_trades: number
  train_cagr: number
  wf_consistency_score: number
  reliability_score: number
  reliability_label: 'Strong evidence' | 'Moderate evidence' | 'Weak evidence' | 'Likely Overfitted' | 'Insufficient Data'
  sensitivity_score: number
  vs_buy_and_hold_cagr: number
  vs_best_single_cagr: number
}

export interface CombinationDetail extends CombinationSummary {
  val_cagr: number
  oos_sortino: number
  oos_median_return_pct: number
  oos_profit_factor: number
  regime_performance: { regime: string; win_rate: number; trade_count: number; cagr: number }[]
  reliability_breakdown: Record<string, number>
  explanation: {
    what_each_captures: string[]
    why_complementary: string
    typical_stocks: string
    works_well_in: string
    struggles_in: string
    risks_and_weaknesses: string
  }
  vs_sma_crossover_cagr: number
}

export interface BestCombinations {
  overall: CombinationSummary
  low_risk: CombinationSummary
  high_growth: CombinationSummary
  most_consistent: CombinationSummary
}

export interface RunStatus {
  status: 'running' | 'complete' | 'failed' | 'never_run'
  last_completed_at: string | null
  last_run_id: number | null
  combinations_tested: number | null
  top_combination: CombinationSummary | null
}

export const getCombinationRankings = (params?: {
  size?: number; regime?: string; sort_by?: string
}): Promise<CombinationSummary[]>

export const getCombinationDetail = (id: number): Promise<CombinationDetail>

export const getBestCombinations = (): Promise<BestCombinations>

export const getCombinationsToAvoid = (): Promise<CombinationSummary[]>

export const getRunStatus = (): Promise<RunStatus>

export const triggerAnalysis = (): Promise<{ status: string; run_id: number }>
```

---

### `CombinationsPage.tsx` — Layout

**Zone 1 — Status bar + "Best Of" cards**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Strategy Combinations   Last run: Sun 22:04  [Re-run Analysis]             │
├────────────────┬────────────────┬────────────────┬────────────────┐
│ Best Overall   │ Best Low-Risk  │ Best Growth    │ Most Consistent │
│ RSI+MACD+ST    │ Graham+Div     │ CANSLIM+BB     │ EMA+SuperTrend  │
│ OOS: 24% CAGR  │ DD: 8%        │ OOS: 31% CAGR  │ WF: 87%        │
│ ★ Strong       │ ★ Strong       │ ◆ Moderate     │ ★ Strong        │
└────────────────┴────────────────┴────────────────┴────────────────┘
```

**Zone 2 — Rankings table with expandable rows**

```
[Size: All ▼] [Regime: All ▼] [Sort: Reliability ▼]

Rank  Strategies              Size  OOS CAGR  Max DD  Sharpe  Win%  Signals  Reliability
 1    RSI + MACD + SuperTrend   3    24.1%    14.2%   1.82   58%     312    ● Strong
 2    EMA Cross + BB Squeeze    2    21.3%    12.8%   1.71   55%     198    ● Strong
 3    CANSLIM + Growth + MFI    3    19.8%    18.4%   1.45   52%     127    ◆ Moderate
...

▼ Expanded row (click to toggle):
┌──────────────────────────────────────┬───────────────────────────────────────┐
│ Score Breakdown                      │ Period Performance                    │
│ OOS Performance      ████████░  28/30│ Period   CAGR  MaxDD  Sharpe  Trades │
│ WF Consistency       ███████░░  18/25│ Train    31.2%  11%   2.10    1,241  │
│ Train→OOS Stability  ███████░░  16/20│ Val      27.4%  13%   1.91      312  │
│ Drawdown Control     █████████  9/10 │ OOS      24.1%  14%   1.82      312  │
│ Signal Sufficiency   ██████████ 10/10│                                       │
│ Regime Coverage      █████      3/5  │ vs Buy-and-Hold:    +11.4%           │
│                      ─────────────── │ vs Best Single:      +5.2%           │
│ TOTAL:               84 / 100        │ vs SMA Crossover:   +15.7%           │
├──────────────────────────────────────┴───────────────────────────────────────┤
│ Regime Performance                                                            │
│ BULL: 63% win, 28% CAGR, 189 trades                                          │
│ SIDEWAYS: 48% win, 12% CAGR, 89 trades                                       │
│ BEAR: 38% win, -3% CAGR, 34 trades                                           │
├───────────────────────────────────────────────────────────────────────────────┤
│ Why This Works                                                                │
│ • RSI: captures momentum exhaustion and reversal at oversold levels           │
│ • MACD: confirms trend direction and momentum with histogram divergence       │
│ • SuperTrend: provides dynamic S/R to filter false breakouts                  │
│ These three capture different market dimensions: momentum state (RSI),        │
│ trend direction (MACD), and price structure (SuperTrend). Low correlation     │
│ (avg 0.28) means each adds independent signal value.                          │
│ Works well in: Trending markets (BULL, STRONG_BULL)                           │
│ Struggles in: Extended sideways chop; generates false breakout signals        │
│ Weakness: Holding period 15–30 days means gap-down risk on earnings           │
└───────────────────────────────────────────────────────────────────────────────┘
```

**Zone 3 — Benchmarks + Avoid section**

```
Benchmark Comparison (OOS Period)
─────────────────────────────────────────────────────────────────────
Name                        CAGR    Max DD   Sharpe   Signals
─────────────────────────────────────────────────────────────────────
#1 RSI + MACD + SuperTrend  24.1%   14.2%    1.82       312
Buy-and-Hold (all symbols)  12.7%   31.4%    0.61         —
Best Single Strategy        18.9%   19.2%    1.34       445
SMA 20/50 Crossover          9.3%   22.1%    0.48       201
─────────────────────────────────────────────────────────────────────

▶ Combinations to Avoid (3)   ← collapsible
  [Shows combinations with Likely Overfitted or Insufficient Data labels]
```

---

### Reliability Badge Colours

| Label | Colour |
|---|---|
| Strong evidence | Emerald (green) |
| Moderate evidence | Blue |
| Weak evidence | Amber |
| Likely Overfitted | Red |
| Insufficient Data | Gray |

---

## What Is NOT Changing

- No changes to existing `BacktestRunner`, `BacktestSimulator`, `compute_metrics`, `WalkForward`, `SignalAggregator` — all reused as-is
- No changes to existing strategy files or `ALL_STRATEGIES`
- No changes to existing frontend pages (Dashboard, Scanner, Backtest, Leaderboard)
- No point-in-time fundamentals store (fundamental strategy OOS metrics are noted as unreliable until deferred phase)
- No ML-based ensemble weighting (deferred — the chosen approach is consensus threshold)
- No portfolio-level position allocation (each combination still evaluates per-signal)
- No Nifty 50 index price data integration (buy-and-hold benchmark uses equal-weight symbol average instead)
