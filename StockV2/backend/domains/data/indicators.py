import numpy as np
import pandas as pd
import ta


class IndicatorEngine:
    """Computes all technical indicators on an OHLCV DataFrame.

    Input columns required: open, high, low, close, volume (lowercase).
    Returns a new DataFrame with all indicator columns appended.
    Does not modify the input DataFrame.
    """

    @staticmethod
    def compute(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df.copy()

        out = df.copy()
        close = out["close"]
        high = out["high"]
        low = out["low"]
        volume = out["volume"].astype(float)
        n = len(df)

        # ── Moving Averages ──────────────────────────────────────────
        out["sma_5"]  = ta.trend.SMAIndicator(close, window=5).sma_indicator()  if n >= 5  else pd.Series(float("nan"), index=close.index)
        out["sma_10"] = ta.trend.SMAIndicator(close, window=10).sma_indicator() if n >= 10 else pd.Series(float("nan"), index=close.index)
        out["sma_20"] = ta.trend.SMAIndicator(close, window=20).sma_indicator() if n >= 20 else pd.Series(float("nan"), index=close.index)
        out["sma_50"] = ta.trend.SMAIndicator(close, window=50).sma_indicator() if n >= 50 else pd.Series(float("nan"), index=close.index)
        out["ema_9"]  = ta.trend.EMAIndicator(close, window=9).ema_indicator()  if n >= 9  else pd.Series(float("nan"), index=close.index)
        out["ema_21"] = ta.trend.EMAIndicator(close, window=21).ema_indicator() if n >= 21 else pd.Series(float("nan"), index=close.index)

        # ── RSI ──────────────────────────────────────────────────────
        out["rsi_14"] = ta.momentum.RSIIndicator(close, window=14).rsi() if n >= 15 else pd.Series(float("nan"), index=close.index)
        out["rsi_9"]  = ta.momentum.RSIIndicator(close, window=9).rsi()  if n >= 10 else pd.Series(float("nan"), index=close.index)
        out["rsi_5"]  = ta.momentum.RSIIndicator(close, window=5).rsi()  if n >= 6  else pd.Series(float("nan"), index=close.index)

        # ── MACD (12, 26, 9) ────────────────────────────────────────
        if n >= 34:
            macd_ind = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
            out["macd"] = macd_ind.macd()
            out["macd_signal"] = macd_ind.macd_signal()
            out["macd_hist"] = macd_ind.macd_diff()
        else:
            out["macd"] = out["macd_signal"] = out["macd_hist"] = pd.Series(float("nan"), index=close.index)

        # ── Bollinger Bands (20, 2) ──────────────────────────────────
        if n >= 20:
            bb_ind = ta.volatility.BollingerBands(close, window=20, window_dev=2)
            out["bb_upper"] = bb_ind.bollinger_hband()
            out["bb_middle"] = bb_ind.bollinger_mavg()
            out["bb_lower"] = bb_ind.bollinger_lband()
        else:
            out["bb_upper"] = out["bb_middle"] = out["bb_lower"] = pd.Series(float("nan"), index=close.index)

        # ── ATR — Wilder's smoothing via EWM to avoid ta library edge cases ──
        out["atr_14"] = IndicatorEngine._atr(high, low, close, window=14) if n >= 14 else pd.Series(float("nan"), index=close.index)

        # ── Volume ───────────────────────────────────────────────────
        out["volume_sma_20"] = ta.trend.SMAIndicator(volume, window=20).sma_indicator() if n >= 20 else pd.Series(float("nan"), index=close.index)
        out["volume_ratio"] = volume / out["volume_sma_20"].replace(0, float("nan"))

        # ── ADX ──────────────────────────────────────────────────────
        out["adx_14"] = ta.trend.ADXIndicator(high, low, close, window=14).adx() if n >= 28 else pd.Series(float("nan"), index=close.index)

        # ── Rate of Change ───────────────────────────────────────────
        out["roc_10"] = ta.momentum.ROCIndicator(close, window=10).roc() if n >= 11 else pd.Series(float("nan"), index=close.index)

        # ── Money Flow Index ─────────────────────────────────────────
        out["mfi_14"] = ta.volume.MFIIndicator(high, low, close, volume, window=14).money_flow_index() if n >= 15 else pd.Series(float("nan"), index=close.index)

        # ── CCI ──────────────────────────────────────────────────────
        out["cci_20"] = ta.trend.CCIIndicator(high, low, close, window=20).cci() if n >= 20 else pd.Series(float("nan"), index=close.index)

        # ── Williams %R ──────────────────────────────────────────────
        out["williams_r"] = ta.momentum.WilliamsRIndicator(high, low, close, lbp=14).williams_r() if n >= 14 else pd.Series(float("nan"), index=close.index)

        # ── SuperTrend (7, 3.0) ──────────────────────────────────────
        if n >= 14:
            out["supertrend"], out["supertrend_direction"] = IndicatorEngine._supertrend(
                high, low, close, period=7, multiplier=3.0
            )
        else:
            out["supertrend"] = out["supertrend_direction"] = pd.Series(float("nan"), index=close.index)

        # ── Fast EMAs ────────────────────────────────────────────────
        out["ema_5"]  = ta.trend.EMAIndicator(close, window=5).ema_indicator()  if n >= 5  else pd.Series(float("nan"), index=close.index)
        out["ema_10"] = ta.trend.EMAIndicator(close, window=10).ema_indicator() if n >= 10 else pd.Series(float("nan"), index=close.index)
        out["ema_13"] = ta.trend.EMAIndicator(close, window=13).ema_indicator() if n >= 13 else pd.Series(float("nan"), index=close.index)
        out["ema_26"] = ta.trend.EMAIndicator(close, window=26).ema_indicator() if n >= 26 else pd.Series(float("nan"), index=close.index)
        out["ema_50"] = ta.trend.EMAIndicator(close, window=50).ema_indicator() if n >= 50 else pd.Series(float("nan"), index=close.index)

        # ── On Balance Volume ────────────────────────────────────────
        obv = (volume * close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))).cumsum()
        out["obv"] = obv
        out["obv_sma_10"] = ta.trend.SMAIndicator(obv, window=10).sma_indicator() if n >= 10 else pd.Series(float("nan"), index=close.index)

        # ── Bollinger Band Width ─────────────────────────────────────
        if n >= 20:
            out["bb_width"] = (out["bb_upper"] - out["bb_lower"]) / out["bb_middle"].replace(0, float("nan"))
            out["bb_width_sma_20"] = ta.trend.SMAIndicator(out["bb_width"], window=20).sma_indicator()
        else:
            out["bb_width"] = out["bb_width_sma_20"] = pd.Series(float("nan"), index=close.index)

        # ── Gap (open vs prev close) ─────────────────────────────────
        out["gap_pct"] = (out["open"] - close.shift(1)) / close.shift(1) * 100

        # ── Stochastic (14, 3) ───────────────────────────────────────
        if n >= 14:
            stoch = ta.momentum.StochasticOscillator(high, low, close, window=14, smooth_window=3)
            out["stoch_k"] = stoch.stoch()
            out["stoch_d"] = stoch.stoch_signal()
        else:
            out["stoch_k"] = out["stoch_d"] = pd.Series(float("nan"), index=close.index)

        # ── ATR ratio (ATR / close) — used for volatility squeeze detection ──
        out["atr_ratio"] = out["atr_14"] / close.replace(0, float("nan")) * 100

        # ── ATR & Volume 5-bar trend (positive = expanding/growing) ──
        out["atr_5bar_change"] = out["atr_14"] - out["atr_14"].shift(5)
        out["volume_sma_5bar_change"] = out["volume_sma_20"] - out["volume_sma_20"].shift(5)

        # ── Additional EMAs ───────────────────────────────────────────────────
        out["ema_7"]  = ta.trend.EMAIndicator(close, window=7).ema_indicator()  if n >= 7  else pd.Series(float("nan"), index=close.index)
        out["ema_14"] = ta.trend.EMAIndicator(close, window=14).ema_indicator() if n >= 14 else pd.Series(float("nan"), index=close.index)
        out["ema_22"] = ta.trend.EMAIndicator(close, window=22).ema_indicator() if n >= 22 else pd.Series(float("nan"), index=close.index)

        # ── Zero-Lag EMA(14): 2·EMA(14) − EMA(7) ─────────────────────────────
        if n >= 14:
            out["zlema_14"] = 2 * out["ema_14"] - out["ema_7"]
        else:
            out["zlema_14"] = pd.Series(float("nan"), index=close.index)

        # ── PSAR (step=0.02, max=0.2) ─────────────────────────────────────────
        if n >= 5:
            _psar_ind = ta.trend.PSARIndicator(high, low, close, step=0.02, max_step=0.2)
            out["psar"]      = _psar_ind.psar()
            out["psar_bull"] = (~_psar_ind.psar_up().isna()).astype(float)
        else:
            out["psar"] = out["psar_bull"] = pd.Series(float("nan"), index=close.index)

        # ── DMI +/− (14) — ADXIndicator also provides these alongside adx_14 ──
        if n >= 28:
            _adx_ind2        = ta.trend.ADXIndicator(high, low, close, window=14)
            out["dmi_plus_14"]  = _adx_ind2.adx_pos()
            out["dmi_minus_14"] = _adx_ind2.adx_neg()
        else:
            out["dmi_plus_14"] = out["dmi_minus_14"] = pd.Series(float("nan"), index=close.index)

        # ── Vortex (14) ───────────────────────────────────────────────────────
        if n >= 15:
            _vortex           = ta.trend.VortexIndicator(high, low, close, window=14)
            out["vortex_pos"] = _vortex.vortex_indicator_pos()
            out["vortex_neg"] = _vortex.vortex_indicator_neg()
        else:
            out["vortex_pos"] = out["vortex_neg"] = pd.Series(float("nan"), index=close.index)

        # ── Fisher Transform (9) ──────────────────────────────────────────────
        if n >= 9:
            _highest  = high.rolling(9).max()
            _lowest   = low.rolling(9).min()
            _hl_rng   = (_highest - _lowest).clip(lower=1e-10)
            _hl2      = (high + low) / 2
            _fval     = ((2 * (_hl2 - _lowest) / _hl_rng) - 1).clip(-0.999, 0.999)
            out["fisher_9"] = 0.5 * np.log((1 + _fval) / (1 - _fval))
        else:
            out["fisher_9"] = pd.Series(float("nan"), index=close.index)

        # ── Donchian Channels (20) ────────────────────────────────────────────
        if n >= 20:
            _dc                    = ta.volatility.DonchianChannel(high, low, close, window=20)
            out["donchian_high_20"] = _dc.donchian_channel_hband()
            out["donchian_low_20"]  = _dc.donchian_channel_lband()
            out["donchian_mid_20"]  = _dc.donchian_channel_mband()
        else:
            out["donchian_high_20"] = out["donchian_low_20"] = out["donchian_mid_20"] = pd.Series(float("nan"), index=close.index)

        # ── Stochastic RSI (14, 14, 3, 3) — result on 0–100 scale ────────────
        if n >= 34:
            _srsi              = ta.momentum.StochRSIIndicator(close, window=14, smooth1=3, smooth2=3)
            out["stoch_rsi_k"] = _srsi.stochrsi_k()
            out["stoch_rsi_d"] = _srsi.stochrsi_d()
        else:
            out["stoch_rsi_k"] = out["stoch_rsi_d"] = pd.Series(float("nan"), index=close.index)

        # ── Chaikin Money Flow (20) ───────────────────────────────────────────
        if n >= 20:
            out["cmf_20"] = ta.volume.ChaikinMoneyFlowIndicator(high, low, close, volume, window=20).chaikin_money_flow()
        else:
            out["cmf_20"] = pd.Series(float("nan"), index=close.index)

        # ── Ichimoku Cloud ────────────────────────────────────────────────────
        if n >= 52:
            _tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
            _kijun  = (high.rolling(26).max() + low.rolling(26).min()) / 2
            _span_a = (_tenkan + _kijun) / 2
            _span_b = (high.rolling(52).max() + low.rolling(52).min()) / 2
            out["ichimoku_tenkan"]  = _tenkan
            out["ichimoku_kijun"]   = _kijun
            out["ichimoku_span_a"]  = _span_a
            out["ichimoku_span_b"]  = _span_b
            out["ichimoku_cloud_a"] = _span_a.shift(26)
            out["ichimoku_cloud_b"] = _span_b.shift(26)
        else:
            for _ic in ["ichimoku_tenkan", "ichimoku_kijun", "ichimoku_span_a",
                        "ichimoku_span_b", "ichimoku_cloud_a", "ichimoku_cloud_b"]:
                out[_ic] = pd.Series(float("nan"), index=close.index)

        # ── Chandelier Exit (22, 3.0): highest_close(22) − 3 × ATR(22) ───────
        if n >= 22:
            out["chandelier_long"] = close.rolling(22).max() - 3.0 * IndicatorEngine._atr(high, low, close, window=22)
        else:
            out["chandelier_long"] = pd.Series(float("nan"), index=close.index)

        # ── Awesome Oscillator + Williams Alligator ───────────────────────────
        if n >= 13:
            _mid = (high + low) / 2
            out["alligator_jaw"]   = _mid.ewm(com=12, adjust=False).mean()  # SMMA(13)
            out["alligator_teeth"] = _mid.ewm(com=7,  adjust=False).mean()  # SMMA(8)
            out["alligator_lips"]  = _mid.ewm(com=4,  adjust=False).mean()  # SMMA(5)
            out["ao"] = _mid.rolling(5).mean() - _mid.rolling(34).mean() if n >= 34 else pd.Series(float("nan"), index=close.index)
        else:
            for _ac in ["alligator_jaw", "alligator_teeth", "alligator_lips", "ao"]:
                out[_ac] = pd.Series(float("nan"), index=close.index)

        # ── Rolling 200-bar high (for CANSLIM 52-week high check) ─────────────
        out["rolling_high_200"] = high.rolling(200, min_periods=100).max()

        # ══════════════════════════════════════════════════════════════════════
        # Strategy-specific precomputed indicators
        # Eliminates O(n²) / GIL-serialised work in run_multi() for 7 strategies
        # that contain Python for-loops. Each is computed ONCE per symbol here.
        # ══════════════════════════════════════════════════════════════════════

        def _rsi_s(ser: pd.Series, period: int) -> pd.Series:
            delta = ser.diff()
            gain  = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
            loss  = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean().clip(lower=1e-10)
            return (100 - 100 / (1 + gain / loss)).fillna(50)

        # ── SMA(200) ──────────────────────────────────────────────────────────
        out["sma_200"] = close.rolling(200, min_periods=100).mean()

        # ── HMA(50) ── vectorised WMA via rolling-apply (runs once, not n times)
        if n >= 56:
            def _wma_s(s: pd.Series, p: int) -> pd.Series:
                w = np.arange(1, p + 1, dtype=float); ws = float(w.sum())
                return s.rolling(p).apply(lambda x: float(np.dot(x, w)) / ws, raw=True)
            _raw_hma = 2.0 * _wma_s(close, 25) - _wma_s(close, 50)
            out["hma_50"] = _wma_s(_raw_hma, 7)
        else:
            out["hma_50"] = pd.Series(float("nan"), index=close.index)

        # ── UT Bot ATR trailing stop (key=1.0, ATR=atr_14) ───────────────────
        if n >= 15:
            _cl_v = close.values; _atr_v = out["atr_14"].values
            _ts = np.zeros(n); _ts[0] = _cl_v[0]
            for _i in range(1, n):
                _c, _pc, _pt = _cl_v[_i], _cl_v[_i - 1], _ts[_i - 1]
                _nl = 0.0 if np.isnan(_atr_v[_i]) else _atr_v[_i]
                if   _c > _pt and _pc > _pt: _ts[_i] = max(_pt, _c - _nl)
                elif _c < _pt and _pc < _pt: _ts[_i] = min(_pt, _c + _nl)
                elif _c > _pt:              _ts[_i] = _c - _nl
                else:                       _ts[_i] = _c + _nl
            out["ut_bot_stop"] = pd.Series(_ts, index=close.index)
        else:
            out["ut_bot_stop"] = pd.Series(float("nan"), index=close.index)

        # ── Squeeze Momentum (BB/KC squeeze + linreg momentum) ───────────────
        if n >= 35:
            _sqz_n  = 20
            _bb_sma = close.rolling(_sqz_n).mean()
            _bb_std = close.rolling(_sqz_n).std(ddof=0)
            _bb_u   = _bb_sma + 2.0 * _bb_std
            _bb_l   = _bb_sma - 2.0 * _bb_std
            _kc_atr = IndicatorEngine._atr(high, low, close, window=_sqz_n)
            _kc_u   = _bb_sma + 1.5 * _kc_atr
            _kc_l   = _bb_sma - 1.5 * _kc_atr
            out["squeeze_on"] = ((_bb_l > _kc_l) & (_bb_u < _kc_u)).astype(float)
            _hi_n   = high.rolling(_sqz_n).max()
            _lo_n   = low.rolling(_sqz_n).min()
            _delta  = close - ((_hi_n + _lo_n) / 2 + _bb_sma) / 2
            _d_v    = _delta.values
            _x_fit  = np.arange(_sqz_n, dtype=float)
            _mom_v  = np.full(n, np.nan)
            for _i in range(_sqz_n - 1, n):
                _y = _d_v[_i - _sqz_n + 1:_i + 1]
                if not np.any(np.isnan(_y)):
                    _cf, _ci = np.polyfit(_x_fit, _y, 1)
                    _mom_v[_i] = float(np.polyval([_cf, _ci], _sqz_n - 1))
            out["squeeze_mom"] = pd.Series(_mom_v, index=close.index)
        else:
            out["squeeze_on"] = out["squeeze_mom"] = pd.Series(float("nan"), index=close.index)

        # ── QQE Mod (fast RSI6/SF4.238, slow RSI14/SF4.238) ─────────────────
        def _qqe_c(cl: pd.Series, rsi_p: int, sf: float) -> tuple[pd.Series, pd.Series]:
            _rm   = _rsi_s(cl, rsi_p).ewm(span=5, adjust=False).mean()
            _w    = rsi_p * 2 - 1
            _dar  = _rm.diff().abs().ewm(com=_w - 1, adjust=False).mean()\
                       .ewm(com=_w - 1, adjust=False).mean() * sf
            _ra   = _rm.values; _da = _dar.values; _qq = np.zeros(len(_ra)); _qq[0] = _ra[0]
            for _i in range(1, len(_ra)):
                _r = _ra[_i]; _d = float(_da[_i]) if not np.isnan(_da[_i]) else 0.0
                _qq[_i] = max(_qq[_i - 1], _r - _d) if _r >= _qq[_i - 1] \
                     else min(_qq[_i - 1], _r + _d)
            return pd.Series(_rm.values, index=cl.index), pd.Series(_qq, index=cl.index)

        if n >= 50:
            _qfr, _qfl = _qqe_c(close, 6,  4.238)
            _qsr, _qsl = _qqe_c(close, 14, 4.238)
            out["qqe_fast_rsi"] = _qfr; out["qqe_fast"] = _qfl
            out["qqe_slow_rsi"] = _qsr; out["qqe_slow"] = _qsl
        else:
            for _q in ("qqe_fast_rsi", "qqe_fast", "qqe_slow_rsi", "qqe_slow"):
                out[_q] = pd.Series(float("nan"), index=close.index)

        # ── Connors RSI ───────────────────────────────────────────────────────
        if n >= 110:
            _rsi3  = _rsi_s(close, 3)
            _clv   = close.values; _sv = np.zeros(n)
            for _i in range(1, n):
                if   _clv[_i] > _clv[_i - 1]: _sv[_i] = max(_sv[_i - 1], 0) + 1
                elif _clv[_i] < _clv[_i - 1]: _sv[_i] = min(_sv[_i - 1], 0) - 1
            _srsi  = _rsi_s(pd.Series(_sv, index=close.index), 2)
            _pret  = close.pct_change()
            def _pr_fn(x):
                p = x[:-1]; t = x[-1]; v = p[~np.isnan(p)]
                return 50.0 if len(v) == 0 or np.isnan(t) else float(np.sum(v < t) / len(v) * 100)
            _prank = _pret.rolling(101).apply(_pr_fn, raw=True)
            out["connors_rsi"] = (_rsi3 + _srsi + _prank) / 3
        else:
            out["connors_rsi"] = pd.Series(float("nan"), index=close.index)

        # ── Nadaraya-Watson Envelope (RQ kernel h=8 α=8 mult=3) ──────────────
        if n >= 50:
            _nw_look = min(100, n)
            _nw_i    = np.arange(_nw_look, dtype=float)
            _nw_w    = (1 + _nw_i ** 2 / (2.0 * 8.0 * 64.0)) ** (-8.0)
            _nw_w   /= _nw_w.sum()
            _clv     = close.values; _yh = np.full(n, np.nan)
            for _i in range(_nw_look - 1, n):
                _seg = _clv[max(0, _i - _nw_look + 1):_i + 1][::-1]
                _ww  = _nw_w[:len(_seg)]; _ww = _ww / _ww.sum()
                _yh[_i] = float(np.dot(_ww, _seg))
            _yh_s       = pd.Series(_yh, index=close.index)
            _nw_mae     = (close - _yh_s).abs().rolling(_nw_look).mean()
            out["nw_yhat"]  = _yh_s
            out["nw_upper"] = _yh_s + 3.0 * _nw_mae
            out["nw_lower"] = _yh_s - 3.0 * _nw_mae
        else:
            for _nc in ("nw_yhat", "nw_upper", "nw_lower"):
                out[_nc] = pd.Series(float("nan"), index=close.index)

        # ── Market Cipher B (WaveTrend 9,13 + RSI-MFI 60) ───────────────────
        if n >= 30:
            _hlc3    = (high + low + close) / 3
            _wt_e1   = _hlc3.ewm(span=9, adjust=False).mean()
            _wt_d    = _hlc3 - _wt_e1
            _wt_e2   = _wt_d.abs().ewm(span=9, adjust=False).mean().clip(lower=1e-10)
            _wt1_raw = (_wt_d / (0.015 * _wt_e2)).ewm(span=13, adjust=False).mean()
            out["mc_wt1"]    = _wt1_raw
            out["mc_wt2"]    = _wt1_raw.rolling(4).mean()
            out["rsimfi_60"] = (_rsi_s(close - out["open"], 60) - 50) * 150
        else:
            for _mc in ("mc_wt1", "mc_wt2", "rsimfi_60"):
                out[_mc] = pd.Series(float("nan"), index=close.index)

        # ── Lorentzian Classification (vectorised simple KNN, max_back=500) ──
        if n >= 60:
            _f1 = out["rsi_14"].values
            _lc_hlc3 = (high + low + close) / 3
            _lc_e1   = _lc_hlc3.ewm(span=10, adjust=False).mean()
            _lc_d    = _lc_hlc3 - _lc_e1
            _lc_e2   = _lc_d.abs().ewm(span=10, adjust=False).mean().clip(lower=1e-10)
            _f2      = (_lc_d / (0.015 * _lc_e2)).ewm(span=11, adjust=False).mean().fillna(0).values
            _f3      = out["cci_20"].values
            _f4      = out["adx_14"].values
            _f5      = out["rsi_9"].values
            _feats   = np.column_stack([_f1, _f2, _f3, _f4, _f5])
            _cmeans  = np.nanmean(_feats, axis=0)
            _nmask   = np.isnan(_feats)
            _feats[_nmask] = np.take(_cmeans, np.where(_nmask)[1])
            _clv     = close.values; _lbl = np.zeros(n, dtype=np.int8)
            for _i in range(n - 4):
                if   _clv[_i + 4] > _clv[_i]: _lbl[_i] =  1
                elif _clv[_i + 4] < _clv[_i]: _lbl[_i] = -1
            _pred  = np.full(n, np.nan, dtype=np.float32)
            _k_nn  = 8; _mb = 500
            _all_c = np.where(np.arange(n) % 4 != 0)[0]   # precompute candidate mask
            for _bar in range(60, n):
                _s = max(0, _bar - _mb)
                _e = max(0, _bar - 4)
                _lo = np.searchsorted(_all_c, _s)
                _hi = np.searchsorted(_all_c, _e)
                _cands = _all_c[_lo:_hi]
                if len(_cands) == 0:
                    continue
                _diffs = np.abs(_feats[_cands] - _feats[_bar])
                _dists = np.sum(np.log1p(_diffs), axis=1)
                _k_eff = min(_k_nn, len(_cands))
                _top   = np.argpartition(_dists, _k_eff - 1)[:_k_eff]
                _pred[_bar] = float(np.sum(_lbl[_cands[_top]]))
            out["lorentzian_pred"] = pd.Series(_pred.astype(np.float64), index=close.index)
        else:
            out["lorentzian_pred"] = pd.Series(float("nan"), index=close.index)

        return out

    @staticmethod
    def _atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
        """ATR using Wilder's EWM smoothing — avoids ta library's initialization edge case."""
        prev_close = close.shift(1)
        true_range = pd.concat([
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        return true_range.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()

    @staticmethod
    def _supertrend(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 7,
        multiplier: float = 3.0,
    ) -> tuple[pd.Series, pd.Series]:
        """SuperTrend indicator. Returns (supertrend_line, direction) where direction=1 is bullish."""
        atr = IndicatorEngine._atr(high, low, close, window=period)
        hl2 = (high + low) / 2

        raw_upper = hl2 + multiplier * atr
        raw_lower = hl2 - multiplier * atr

        supertrend = pd.Series(float("nan"), index=close.index)
        direction = pd.Series(float("nan"), index=close.index)

        final_upper = raw_upper.copy()
        final_lower = raw_lower.copy()

        for i in range(1, len(close)):
            if pd.isna(atr.iloc[i]):
                continue

            if raw_lower.iloc[i] > final_lower.iloc[i - 1] or close.iloc[i - 1] < final_lower.iloc[i - 1]:
                final_lower.iloc[i] = raw_lower.iloc[i]
            else:
                final_lower.iloc[i] = final_lower.iloc[i - 1]

            if raw_upper.iloc[i] < final_upper.iloc[i - 1] or close.iloc[i - 1] > final_upper.iloc[i - 1]:
                final_upper.iloc[i] = raw_upper.iloc[i]
            else:
                final_upper.iloc[i] = final_upper.iloc[i - 1]

            prev_st = supertrend.iloc[i - 1]
            if pd.isna(prev_st):
                supertrend.iloc[i] = final_lower.iloc[i]
                direction.iloc[i] = 1.0
            elif prev_st == final_upper.iloc[i - 1]:
                if close.iloc[i] <= final_upper.iloc[i]:
                    supertrend.iloc[i] = final_upper.iloc[i]
                    direction.iloc[i] = -1.0
                else:
                    supertrend.iloc[i] = final_lower.iloc[i]
                    direction.iloc[i] = 1.0
            else:
                if close.iloc[i] >= final_lower.iloc[i]:
                    supertrend.iloc[i] = final_lower.iloc[i]
                    direction.iloc[i] = 1.0
                else:
                    supertrend.iloc[i] = final_upper.iloc[i]
                    direction.iloc[i] = -1.0

        return supertrend, direction
