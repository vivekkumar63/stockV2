"""
Template for Special Strategies.

Special strategies differ from regular strategies in one key way:
  - Buy entry is triggered by an indicator condition (buy_signal returns BUY)
  - Sell exit is triggered by an indicator condition (sell_signal returns True)
  - There is NO stop-loss price, NO target price, NO max holding days
  - The position is held until the sell condition fires or the backtest ends

To create a new special strategy:
  1. Copy this file to a new .py file in this directory (no leading underscore)
  2. Define a class inheriting SpecialBaseStrategy
  3. Set a unique `name` and `description`
  4. Implement buy_signal(df) -> SpecialSignal
  5. Implement sell_signal(df) -> bool
  6. Restart the backend — auto-discovery handles the rest

Available columns in df (after IndicatorEngine.compute):
  OHLCV : open, high, low, close, volume
  SMAs  : sma_5, sma_10, sma_20, sma_50, sma_200
  EMAs  : ema_5, ema_7, ema_9, ema_10, ema_13, ema_14, ema_21, ema_22, ema_26, ema_50
  RSI   : rsi_5, rsi_9, rsi_14
  MACD  : macd, macd_signal, macd_hist
  BB    : bb_upper, bb_middle, bb_lower, bb_width, bb_width_sma_20
  ATR   : atr_14, atr_ratio, atr_5bar_change
  ADX   : adx_14, dmi_plus_14, dmi_minus_14
  Trend : supertrend, supertrend_direction, psar, psar_bull
  Stoch : stoch_k, stoch_d, stoch_rsi_k, stoch_rsi_d
  Volume: volume_sma_20, volume_ratio, obv, obv_sma_10
  Other : ichimoku_*, chandelier_long, ao, alligator_*, donchian_*, etc.

Example usage:

    class MySpecialStrategy(SpecialBaseStrategy):
        name = "My Special Strategy"
        description = "Describe entry and exit conditions here."

        def buy_signal(self, df: pd.DataFrame) -> SpecialSignal:
            if len(df) < 3:
                return SpecialSignal("NONE")
            # ... check condition ...
            return SpecialSignal("BUY", confidence=0.7, conditions_met=["Reason text"])

        def sell_signal(self, df: pd.DataFrame) -> bool:
            if len(df) < 3:
                return False
            # ... check exit condition ...
            return some_condition
"""
