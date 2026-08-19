import pandas as pd
from domains.strategies.base import BaseStrategy, Signal, StrategyType, Timeframe


class PullbackUptrend70Strategy(BaseStrategy):
    name = "Pullback in Uptrend (70%+ WR)"
    description = "High win-rate strategy: buy RSI oversold + volume spike in confirmed uptrends"
    strategy_type = StrategyType.TECHNICAL
    timeframe = Timeframe.DAILY
    min_holding_days = 3
    max_holding_days = 12
    weight = 0.20

    def generate_signal(self, df: pd.DataFrame, fundamentals: dict | None = None) -> Signal:
        required = ["rsi_14", "sma_50", "close", "volume_ratio", "adx_14", "bb_lower"]
        if len(df) < 60 or not all(col in df.columns for col in required):
            return Signal(
                signal_type="NONE",
                conditions_failed=["Insufficient data or missing indicators"],
            )

        curr = df.iloc[-1]
        rsi = curr["rsi_14"]
        close = curr["close"]
        sma_50 = curr["sma_50"]
        volume_ratio = curr["volume_ratio"]
        adx = curr["adx_14"]
        bb_lower = curr["bb_lower"]

        if any(pd.isna(x) for x in [rsi, close, sma_50, volume_ratio, adx, bb_lower]):
            return Signal(
                signal_type="NONE",
                conditions_failed=["Missing indicator values"],
            )

        conditions_met = []
        conditions_failed = []

        # Filter 1: RSI oversold
        if rsi < 35:
            conditions_met.append(f"RSI={rsi:.1f} < 35 (oversold)")
        else:
            conditions_failed.append(f"RSI={rsi:.1f} not oversold")

        # Filter 2: Price above SMA 50 (uptrend context)
        pct_above_sma50 = ((close - sma_50) / sma_50) * 100
        if close > sma_50:
            conditions_met.append(f"Price {pct_above_sma50:.1f}% above SMA50 (uptrend)")
        else:
            conditions_failed.append(f"Price {pct_above_sma50:.1f}% below SMA50 (downtrend)")

        # Filter 3: Volume spike (buying pressure on dip)
        if volume_ratio > 1.5:
            conditions_met.append(f"Volume {volume_ratio:.1f}x average (spike)")
        else:
            conditions_failed.append(f"Volume only {volume_ratio:.1f}x average (weak)")

        # Filter 4: ADX not too high (avoid strong downtrends)
        if adx < 35:
            conditions_met.append(f"ADX={adx:.1f} < 35 (no strong trend)")
        else:
            conditions_failed.append(f"ADX={adx:.1f} too high (strong trend)")

        # Filter 5: Close above lower BB (not in free-fall)
        pct_above_bb = ((close - bb_lower) / bb_lower) * 100
        if close > bb_lower:
            conditions_met.append(f"Close {pct_above_bb:.1f}% above BB lower (controlled dip)")
        else:
            conditions_failed.append(f"Close below BB lower (free-fall)")

        # BUY signal only if ALL 5 conditions met
        if len(conditions_met) == 5:
            # Calculate confidence based on how strong the setup is
            rsi_strength = (35 - rsi) / 35  # 0 to 1 as RSI drops from 35 to 0
            volume_strength = min((volume_ratio - 1.5) / 1.5, 1.0)  # 0 to 1 as volume exceeds 1.5x
            confidence = 0.60 + (0.20 * rsi_strength) + (0.15 * volume_strength)
            confidence = min(confidence, 0.95)

            return Signal(
                signal_type="BUY",
                confidence=round(confidence, 4),
                risk_score=0.35,  # Lower risk due to multiple confirmations
                expected_upside_pct=8.0,
                stop_loss_pct=5.0,  # Tight stop (important for high WR)
                target_pct=8.0,  # Conservative target (1.6:1 reward/risk)
                holding_days=8,
                conditions_met=conditions_met,
            )

        return Signal(
            signal_type="NONE",
            conditions_met=conditions_met,
            conditions_failed=conditions_failed,
        )

    def get_required_indicators(self) -> list[str]:
        return ["rsi_14", "sma_50", "close", "volume_ratio", "adx_14", "bb_lower"]

    def get_parameters(self) -> dict:
        return {
            "rsi_threshold": 35,
            "volume_threshold": 1.5,
            "adx_max": 35,
            "stop_loss_pct": 5.0,
            "target_pct": 8.0,
        }
