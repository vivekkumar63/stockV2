import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_DIV_YIELD_MIN  = 0.02   # minimum dividend yield (decimal)
_ROE_MIN        = 0.12   # minimum ROE for dividend payers (decimal)
_DE_MAX         = 0.5    # maximum D/E ratio (conservative)
_BUY_CONFIDENCE = 0.70   # fixed confidence when all 4 criteria met


class DividendInvestingStrategy(BaseStrategy):
    name = "Dividend Investing"
    description = (
        "High-quality dividend payers: yield > 2%, EPS > 0 (covered), ROE > 12%, D/E < 0.5."
    )
    strategy_type = StrategyType.FUNDAMENTAL
    timeframe = Timeframe.DAILY
    min_holding_days = 30
    max_holding_days = 365
    weight = 0.05

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if not fundamentals:
            return Signal("NONE")

        div_yield = fundamentals.get("dividend_yield")
        eps       = fundamentals.get("eps")
        roe       = fundamentals.get("roe")
        de        = fundamentals.get("debt_equity")

        met    = []
        missed = []

        if div_yield is not None and div_yield > _DIV_YIELD_MIN:
            met.append(f"Dividend yield {div_yield*100:.1f}% > {_DIV_YIELD_MIN*100:.0f}%")
        else:
            missed.append(f"Dividend yield <= {_DIV_YIELD_MIN*100:.0f}% or unknown")

        if eps is not None and eps > 0:
            met.append(f"EPS {eps:.1f} > 0 (dividend covered)")
        else:
            missed.append("EPS <= 0 — dividend sustainability risk")

        if roe is not None and roe > _ROE_MIN:
            met.append(f"ROE {roe*100:.1f}% > {_ROE_MIN*100:.0f}%")
        else:
            missed.append(f"ROE <= {_ROE_MIN*100:.0f}% or unknown")

        if de is not None and de < _DE_MAX:
            met.append(f"D/E {de:.2f} < {_DE_MAX} (conservative)")
        else:
            missed.append(f"D/E >= {_DE_MAX} or unknown")

        if len(met) == 4:
            return Signal(
                signal_type="BUY",
                confidence=_BUY_CONFIDENCE,
                risk_score=0.20,
                expected_upside_pct=12.0,
                stop_loss_pct=6.0,
                target_pct=12.0,
                holding_days=90,
                conditions_met=met,
                conditions_failed=missed,
            )
        return Signal("NONE", conditions_met=met, conditions_failed=missed)

    def get_required_indicators(self) -> list[str]:
        return []
