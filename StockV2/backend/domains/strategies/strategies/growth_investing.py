import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe

_ROE_MIN        = 0.15   # minimum ROE (decimal)
_PE_MAX         = 40.0   # maximum P/E for growth stock
_DE_MAX         = 1.0    # maximum D/E ratio
_BUY_THRESHOLD  = 4      # minimum criteria met to issue BUY
_TOTAL_CRITERIA = 5      # total criteria evaluated


class GrowthInvestingStrategy(BaseStrategy):
    name = "Growth Investing"
    description = (
        "GARP (Growth at a Reasonable Price): ROE>15%, EPS>0, PE<40, D/E<1.0, profit>0. "
        "Buy quality growth companies at reasonable valuations."
    )
    strategy_type = StrategyType.FUNDAMENTAL
    timeframe = Timeframe.DAILY
    min_holding_days = 20
    max_holding_days = 60
    weight = 0.05

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if not fundamentals:
            return Signal("NONE")

        roe    = fundamentals.get("roe")
        eps    = fundamentals.get("eps")
        pe     = fundamentals.get("pe_ratio")
        de     = fundamentals.get("debt_equity")
        profit = fundamentals.get("net_profit")

        met    = []
        missed = []

        if roe is not None and roe > _ROE_MIN:
            met.append(f"ROE {roe*100:.1f}% > {_ROE_MIN*100:.0f}%")
        else:
            missed.append(f"ROE <= {_ROE_MIN*100:.0f}% or unknown")

        if eps is not None and eps > 0:
            met.append(f"EPS {eps:.1f} > 0 (profitable)")
        else:
            missed.append("EPS <= 0 or unknown")

        if pe is not None and pe < _PE_MAX:
            met.append(f"PE {pe:.1f} < {_PE_MAX:.0f} (reasonable)")
        else:
            missed.append(f"PE >= {_PE_MAX:.0f} or unknown")

        if de is not None and de < _DE_MAX:
            met.append(f"D/E {de:.2f} < {_DE_MAX:.1f}")
        else:
            missed.append(f"D/E >= {_DE_MAX:.1f} or unknown")

        if profit is not None and profit > 0:
            met.append(f"Net profit {profit:.0f} > 0")
        else:
            missed.append("Net profit <= 0 or unknown")

        if len(met) >= _BUY_THRESHOLD:
            confidence = round(len(met) / _TOTAL_CRITERIA, 4)
            return Signal(
                signal_type="BUY",
                confidence=confidence,
                risk_score=0.35,
                expected_upside_pct=20.0,
                stop_loss_pct=8.0,
                target_pct=20.0,
                holding_days=30,
                conditions_met=met,
                conditions_failed=missed,
            )
        return Signal("NONE", conditions_met=met, conditions_failed=missed)

    def get_required_indicators(self) -> list[str]:
        return []
