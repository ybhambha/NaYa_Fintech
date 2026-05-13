"""
semisector/indicators.py
────────────────────────
IndicatorEngine — computes all technical indicators from a TickerData
instance and exposes them as typed attributes, including the composite
Opportunity Score (0–100).
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from ta.trend    import MACD, SMAIndicator, ADXIndicator, EMAIndicator
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands, AverageTrueRange

from semisector.config import (
    RSI_WINDOW, RSI_SLOW_WINDOW, BB_WINDOW, BB_STD,
    ADX_WINDOW, ATR_WINDOW, STOCH_WINDOW,
    SMA_SHORT, SMA_MID, SMA_LONG, EMA_WINDOW,
    SUPPORT_LOOKBACK, RISK_FREE_RATE,
    ADX_STRONG,
)
from semisector.ticker_data import TickerData


class IndicatorEngine:
    """
    Computes RSI, MACD, Bollinger Bands, SMAs, EMA, ADX, ATR,
    Stochastic, VWAP, rolling returns, volatility, Sharpe ratio,
    max drawdown, and the composite Opportunity Score.

    Usage:
        ind = IndicatorEngine(ticker_data)
        print(ind.score, ind.rsi, ind.trend)
    """

    def __init__(self, td: TickerData) -> None:
        if not td.is_valid:
            raise ValueError(f"TickerData for {td.ticker} has no OHLCV data.")
        self._td  = td
        self._df  = td.ohlcv.copy()
        self._compute()

    # ── Private helpers ───────────────────────────────────────────────────────

    def _flt(self, col: str) -> float:
        v = self._df.iloc[-1][col]
        return float(v) if not pd.isna(v) else 0.0

    def _ret(self, days: int) -> Optional[float]:
        """Percentage return over the last `days` trading days."""
        idx = max(0, len(self._df) - days - 1)
        p0  = float(self._df.iloc[idx]["close"])
        return (self.price / p0 - 1) * 100 if p0 else None

    # ── Main computation ──────────────────────────────────────────────────────

    def _compute(self) -> None:
        df    = self._df
        close = df["close"]
        high  = df["high"]
        low   = df["low"]
        vol   = df.get("volume")

        # ── Momentum ──────────────────────────────────────────────────────────
        df["rsi"]       = RSIIndicator(close, window=RSI_WINDOW).rsi()
        df["rsi_slow"]  = RSIIndicator(close, window=RSI_SLOW_WINDOW).rsi()
        _macd           = MACD(close)
        df["macd"]      = _macd.macd()
        df["macd_sig"]  = _macd.macd_signal()
        df["macd_hist"] = _macd.macd_diff()
        _stoch          = StochasticOscillator(high, low, close,
                                               window=STOCH_WINDOW)
        df["stoch_k"]   = _stoch.stoch()
        df["stoch_d"]   = _stoch.stoch_signal()

        # ── Trend ─────────────────────────────────────────────────────────────
        df["sma20"]  = SMAIndicator(close, window=SMA_SHORT).sma_indicator()
        df["sma50"]  = SMAIndicator(close, window=SMA_MID).sma_indicator()
        df["sma200"] = SMAIndicator(close, window=SMA_LONG).sma_indicator()
        df["ema21"]  = EMAIndicator(close, window=EMA_WINDOW).ema_indicator()
        df["adx"]    = ADXIndicator(high, low, close,
                                    window=ADX_WINDOW).adx()

        # ── Volatility ────────────────────────────────────────────────────────
        _bb             = BollingerBands(close, window=BB_WINDOW,
                                         window_dev=BB_STD)
        df["bb_upper"]  = _bb.bollinger_hband()
        df["bb_lower"]  = _bb.bollinger_lband()
        df["bb_mid"]    = _bb.bollinger_mavg()
        df["bb_pct"]    = _bb.bollinger_pband()
        df["bb_width"]  = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]
        df["atr"]       = AverageTrueRange(high, low, close,
                                           window=ATR_WINDOW).average_true_range()

        # ── VWAP (cumulative approximation) ───────────────────────────────────
        if vol is not None and vol.sum() > 0:
            df["vwap"] = (close * vol).cumsum() / vol.cumsum()
        else:
            df["vwap"] = df["sma20"]

        # ── Snapshot (last bar) ───────────────────────────────────────────────
        self.price     = float(df.iloc[-1]["close"])
        self.rsi       = self._flt("rsi")
        self.macd_hist = self._flt("macd_hist")
        self.bb_pct    = self._flt("bb_pct")
        self.bb_width  = self._flt("bb_width")
        self.bb_upper  = self._flt("bb_upper")
        self.bb_lower  = self._flt("bb_lower")
        self.sma20     = self._flt("sma20")
        self.sma50     = self._flt("sma50")
        self.sma200    = self._flt("sma200")
        self.ema21     = self._flt("ema21")
        self.adx       = self._flt("adx")
        self.atr       = self._flt("atr")
        self.stoch_k   = self._flt("stoch_k")
        self.vwap      = self._flt("vwap")

        # ── Returns ───────────────────────────────────────────────────────────
        self.ret_1w  = self._ret(5)
        self.ret_1m  = self._ret(21)
        self.ret_3m  = self._ret(63)
        self.ret_6m  = self._ret(126)
        self.ret_1y  = self._ret(252)

        # ── Risk metrics ──────────────────────────────────────────────────────
        daily_rets       = close.pct_change().dropna()
        self.vol_30d_ann = float(daily_rets.tail(30).std() * np.sqrt(252) * 100)
        rolling_max      = close.cummax()
        self.max_dd      = float(((close - rolling_max) / rolling_max).min() * 100)
        rf_daily         = RISK_FREE_RATE / 252
        excess           = daily_rets - rf_daily
        self.sharpe_est  = (
            float(excess.mean() / excess.std() * np.sqrt(252))
            if excess.std() > 0 else None
        )

        # ── Distance from key levels ──────────────────────────────────────────
        self.pct_from_50sma  = (self.price / self.sma50  - 1) * 100 if self.sma50  else None
        self.pct_from_200sma = (self.price / self.sma200 - 1) * 100 if self.sma200 else None
        self.pct_from_vwap   = (self.price / self.vwap   - 1) * 100 if self.vwap   else None

        # ── Support / resistance (60-day percentile) ──────────────────────────
        self.support    = float(low.tail(SUPPORT_LOOKBACK).quantile(0.05))
        self.resistance = float(high.tail(SUPPORT_LOOKBACK).quantile(0.95))

        # ── Derived flags ─────────────────────────────────────────────────────
        self.golden_cross = (self.price > self.sma50 > self.sma200)

        # ── Trend label ───────────────────────────────────────────────────────
        if   self.price > self.sma50 > self.sma200: self.trend = "Strong Uptrend ▲▲"
        elif self.price > self.sma50:               self.trend = "Uptrend ▲"
        elif self.price > self.sma200:              self.trend = "Above 200-SMA ↗"
        elif self.price > self.sma200 * 0.95:       self.trend = "Near Support ↔"
        else:                                        self.trend = "Below SMAs ▼"

        self._compute_score()

    def _compute_score(self) -> None:
        """Build the 0–100 composite Opportunity Score."""
        score: int = 0
        detail: dict[str, int] = {}

        # RSI component
        if   self.rsi < 35: pts = 10
        elif self.rsi < 50: pts = 30
        elif self.rsi < 58: pts = 25
        elif self.rsi < 68: pts = 12
        else:               pts = 0
        score += pts; detail["RSI"] = pts

        # Bollinger Band position
        pts = max(0, min(20, int((1 - min(self.bb_pct, 1.2)) * 20)))
        score += pts; detail["BB"] = pts

        # Above 50-day SMA
        pts = 20 if self.price > self.sma50 else 0
        score += pts; detail["SMA50"] = pts

        # MACD histogram positive
        pts = 15 if self.macd_hist > 0 else 0
        score += pts; detail["MACD"] = pts

        # ADX trend strength
        if   self.adx > 30: pts = 15
        elif self.adx > 25: pts = 10
        elif self.adx > 20: pts = 5
        else:               pts = 0
        score += pts; detail["ADX"] = pts

        # Bonuses
        if self.golden_cross:
            score = min(100, score + 5); detail["GoldenX"] = 5
        if self.stoch_k < 60:
            score = min(100, score + 5); detail["Stoch"] = 5

        self.score        = score
        self.score_detail = detail
