import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class SwingTrendRiderStrategy(BaseStrategy):
    name = "Swing Trade Trend Rider"
    description = "Multi-condition confluence: price > SMA50, RSI 50-65, ADX > 20, MACD positive, SuperTrend bullish"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 7
    max_holding_days = 21

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["sma_50", "rsi_14", "adx_14", "macd_hist", "supertrend_direction"]
        if df.empty or not all(c in df.columns for c in required):
            return Signal("NONE")
        row = df.iloc[-1]
        close = row["close"]
        sma_50 = row["sma_50"]
        rsi = row["rsi_14"]
        adx = row["adx_14"]
        macd_hist = row["macd_hist"]
        st_dir = row["supertrend_direction"]
        if any(pd.isna(x) for x in [close, sma_50, rsi, adx, macd_hist, st_dir]):
            return Signal("NONE")
        conditions = {
            f"Close {close:.2f} > SMA50 {sma_50:.2f}": close > sma_50,
            f"RSI={rsi:.1f} in 50–65 (momentum building)": 50 <= rsi <= 65,
            f"ADX={adx:.1f} > 20 (trend established)": adx > 20,
            f"MACD histogram {macd_hist:.4f} > 0": macd_hist > 0,
            "SuperTrend bullish (direction=1)": st_dir == 1.0,
        }
        met = [c for c, v in conditions.items() if v]
        failed = [c for c, v in conditions.items() if not v]
        if len(met) >= 4:
            confidence = min(1.0, 0.50 + len(met) * 0.10)
            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.40,
                expected_upside_pct=14.0,
                stop_loss_pct=7.0,
                target_pct=16.0,
                holding_days=15,
                conditions_met=met,
                conditions_failed=failed,
            )
        return Signal("NONE")

    def get_required_indicators(self) -> list[str]:
        return ["sma_50", "rsi_14", "adx_14", "macd_hist", "supertrend_direction"]
