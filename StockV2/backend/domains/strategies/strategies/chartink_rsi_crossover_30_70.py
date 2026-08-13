import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class ChartinkRSICrossover3070(BaseStrategy):
    """Chartink: Daily RSI Oversold/Overbought — RSI crosses above 30 (BUY) or below 70 (SELL)."""
    name = "Chartink RSI Oversold/Overbought Crossover"
    description = "RSI crosses above 30 from oversold = BUY; RSI crosses below 70 from overbought = SELL"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 2
    max_holding_days = 10

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        if len(df) < 16:
            return Signal("NONE")

        r = df.iloc[-1]
        r_prev = df.iloc[-2]

        c = float(r["close"])
        rsi_now = r["rsi_14"]
        rsi_prev = r_prev["rsi_14"]
        vol_ratio = r["volume_ratio"]
        sma20 = r["sma_20"]

        if any(pd.isna(x) for x in [rsi_now, rsi_prev, vol_ratio]):
            return Signal("NONE")

        met, failed = [], []

        # BUY path: RSI crossed above 30 (bounce from oversold)
        crossed_above_30 = rsi_prev < 30 and rsi_now >= 30
        crossed_below_70 = rsi_prev > 70 and rsi_now <= 70

        if crossed_above_30:
            met.append(f"RSI crossed above 30: {rsi_prev:.1f} → {rsi_now:.1f} (oversold bounce!)")
        elif rsi_now > 30 and rsi_now < 50:
            met.append(f"RSI {rsi_now:.1f} recovering from oversold territory")
        else:
            failed.append(f"RSI {rsi_now:.1f} not crossing from oversold (need cross above 30)")

        if crossed_below_70:
            # Switch to SELL path
            sell_met, sell_failed = [], []
            sell_met.append(f"RSI crossed below 70: {rsi_prev:.1f} → {rsi_now:.1f} (overbought reversal!)")

            if vol_ratio > 1.0:
                sell_met.append(f"Volume {vol_ratio:.2f}x (distribution)")
            else:
                sell_failed.append(f"Low volume {vol_ratio:.2f}x")

            if not pd.isna(sma20) and c > sma20:
                sell_met.append(f"Still above SMA20 {sma20:.1f} (top area)")
            elif not pd.isna(sma20):
                sell_failed.append(f"Already broken below SMA20")

            if len(sell_met) < 2:
                return Signal("NONE", conditions_met=sell_met, conditions_failed=sell_failed)

            confidence = min(0.78, 0.52 + (rsi_prev - 70) / 50 + (len(sell_met) - 2) * 0.05)
            return Signal(
                signal_type="SELL",
                confidence=round(confidence, 4),
                risk_score=0.50,
                expected_upside_pct=0.0,
                stop_loss_pct=0.0,
                target_pct=0.0,
                holding_days=0,
                conditions_met=sell_met,
                conditions_failed=sell_failed,
            )

        if not crossed_above_30 and rsi_now >= 50:
            failed.append(f"RSI {rsi_now:.1f} not in oversold bounce zone")
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        if vol_ratio > 1.0:
            met.append(f"Volume {vol_ratio:.2f}x (buyers returning)")
        else:
            failed.append(f"Low volume {vol_ratio:.2f}x on bounce")

        if not pd.isna(sma20) and c < sma20:
            met.append(f"Close {c:.1f} still below SMA20 {sma20:.1f} (early recovery, upside potential)")
        elif not pd.isna(sma20):
            met.append(f"Close {c:.1f} back above SMA20 {sma20:.1f}")

        if len(met) < 2:
            return Signal("NONE", conditions_met=met, conditions_failed=failed)

        confidence = min(0.78, 0.50 + (30 - rsi_prev) / 50 + (len(met) - 2) * 0.05)

        return Signal(
            signal_type="BUY",
            confidence=round(confidence, 4),
            risk_score=0.50,
            expected_upside_pct=6.0,
            stop_loss_pct=4.0,
            target_pct=8.0,
            holding_days=7,
            conditions_met=met,
            conditions_failed=failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14", "volume_ratio", "sma_20"]
