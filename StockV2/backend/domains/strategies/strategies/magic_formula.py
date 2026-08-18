import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_EARNINGS_YIELD_MIN = 0.06   # EPS/price minimum
_ROE_MIN            = 0.15   # minimum ROE (decimal)
_PE_MAX             = 20.0   # maximum P/E ratio
_DE_MAX             = 1.0    # maximum D/E ratio
_BUY_CONFIDENCE     = 0.75   # fixed confidence when all 4 criteria met


class MagicFormulaStrategy(BaseStrategy):
    name = "Magic Formula"
    description = (
        "Greenblatt Magic Formula: high earnings yield + high return on capital. "
        "Earnings Yield = EPS/price > 6%, ROE > 15%, PE < 20, D/E < 1.0."
    )
    strategy_type = StrategyType.FUNDAMENTAL
    timeframe = Timeframe.DAILY
    min_holding_days = 30
    max_holding_days = 90
    weight = 0.05

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if not fundamentals:
            return Signal("NONE")

        eps = fundamentals.get("eps")
        roe = fundamentals.get("roe")
        pe  = fundamentals.get("pe_ratio")
        de  = fundamentals.get("debt_equity")

        if df.empty:
            return Signal("NONE")

        close = float(df["close"].iloc[-1])
        if close <= 0:
            return Signal("NONE")

        met    = []
        missed = []

        if eps is not None and eps / close > _EARNINGS_YIELD_MIN:
            met.append(f"Earnings yield {eps/close*100:.1f}% > {_EARNINGS_YIELD_MIN*100:.0f}%")
        else:
            missed.append(f"Earnings yield <= {_EARNINGS_YIELD_MIN*100:.0f}%")

        if roe is not None and roe > _ROE_MIN:
            met.append(f"ROE {roe*100:.1f}% > {_ROE_MIN*100:.0f}%")
        else:
            missed.append(f"ROE <= {_ROE_MIN*100:.0f}% or unknown")

        if pe is not None and pe < _PE_MAX:
            met.append(f"PE {pe:.1f} < {_PE_MAX:.0f}")
        else:
            missed.append(f"PE >= {_PE_MAX:.0f} or unknown")

        if de is not None and de < _DE_MAX:
            met.append(f"D/E {de:.2f} < {_DE_MAX:.1f}")
        else:
            missed.append(f"D/E >= {_DE_MAX:.1f} or unknown")

        if len(met) == 4:
            return Signal(
                signal_type="BUY",
                confidence=_BUY_CONFIDENCE,
                risk_score=0.30,
                expected_upside_pct=25.0,
                stop_loss_pct=8.0,
                target_pct=25.0,
                holding_days=45,
                conditions_met=met,
                conditions_failed=missed,
            )
        return Signal("NONE", conditions_met=met, conditions_failed=missed)

    def get_required_indicators(self) -> list[str]:
        return []
