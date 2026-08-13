import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkBTSTBBBreakout(BaseStrategy):
    """Chartink: BOSS BTST — closing above BB upper band with RSI>60 + MACD bullish + green candle."""
    name = "Chartink BTST Bollinger Breakout"
    description = "Close > BB upper + RSI>60 + MACD bullish + volume surge + green candle"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 1
    max_holding_days = 5

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 35:
            return Signal("NONE")

        r = df.iloc[-1]
        c = float(r["close"])
        o = float(r["open"])

        bb_upper = r["bb_upper"]
        rsi = r["rsi_14"]
        macd = r["macd"]
        macd_sig = r["macd_signal"]
        vol_ratio = r["volume_ratio"]
        st_dir = r["supertrend_direction"]

        if any(pd.isna(x) for x in [bb_upper, rsi, macd, macd_sig, vol_ratio]):
            return Signal("NONE")

        met, failed = [], []

        if c > bb_upper:
            pct_above = (c / bb_upper - 1) * 100
            met.append(f"Close {c:.1f} above BB upper {bb_upper:.1f} (+{pct_above:.2f}%)")
        else:
            failed.append(f"Close {c:.1f} below BB upper {bb_upper:.1f}")

        if rsi > 60:
            met.append(f"RSI {rsi:.1f} > 60 (strong momentum)")
        else:
            failed.append(f"RSI {rsi:.1f} < 60")

        if macd > macd_sig:
            met.append(f"MACD {macd:.3f} > signal {macd_sig:.3f}")
        else:
            failed.append(f"MACD bearish ({macd:.3f} < {macd_sig:.3f})")

        if vol_ratio > 1.0:
            met.append(f"Volume {vol_ratio:.2f}x above average")
        else:
            failed.append(f"Low volume ({vol_ratio:.2f}x)")

        if c > o:
            met.append(f"Green candle +{(c/o - 1)*100:.2f}%")
        else:
            failed.append("Red candle")

        if not pd.isna(st_dir) and st_dir == 1.0:
            met.append("SuperTrend bullish")
        else:
            failed.append("SuperTrend not bullish")

        if len(met) < 4:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        confidence = min(0.90, 0.60 + len(met) * 0.05)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.50,
            expected_upside_pct=5.0,
            stop_loss_pct=3.0,
            target_pct=5.0,
            holding_days=3,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["bb_upper", "rsi_14", "macd", "macd_signal", "volume_ratio", "supertrend_direction"]
