"""
semisector/backtester.py
─────────────────────────
Backtester — tests how well the current (or optimized) scoring system
has predicted forward returns historically.

How it works
────────────
For every trading day in the historical price series (rolling window):
  1. Compute all indicators as of that day
  2. Record the score
  3. Measure the actual forward return (1-week, 1-month, 3-month)
  4. Bucket scores into ranges (0-40, 40-55, 55-70, 70-100)
  5. Calculate hit rate and average return per bucket

Output
──────
  BacktestResult — per-ticker backtest statistics
  BacktestReport — aggregated report across all tickers
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from ta.trend     import MACD, SMAIndicator, ADXIndicator
from ta.momentum  import RSIIndicator, StochasticOscillator
from ta.volatility import BollingerBands, AverageTrueRange

from semisector.config    import (
    RSI_WINDOW, BB_WINDOW, BB_STD, ADX_WINDOW, ATR_WINDOW,
    STOCH_WINDOW, SMA_MID, SMA_LONG, RISK_FREE_RATE,
)
from semisector.ticker_data import TickerData


# ── Score bucket labels ───────────────────────────────────────────────────────
BUCKETS = [
    (0,  40,  "Poor  (0–40)"),
    (40, 55,  "Fair  (40–55)"),
    (55, 70,  "Good  (55–70)"),
    (70, 101, "Strong (70–100)"),
]


@dataclass
class BucketStats:
    """Statistics for one score bucket."""
    label:        str
    count:        int   = 0
    hit_rate_1m:  float = 0.0   # % of times 1-month forward return > 0
    hit_rate_3m:  float = 0.0
    avg_ret_1m:   float = 0.0   # average 1-month forward return
    avg_ret_3m:   float = 0.0
    avg_ret_1w:   float = 0.0
    sharpe_1m:    float = 0.0   # Sharpe of 1-month forward returns in bucket


@dataclass
class BacktestResult:
    """Full backtest result for one ticker."""
    ticker:         str
    period:         str
    total_signals:  int                  = 0
    bucket_stats:   list[BucketStats]    = field(default_factory=list)
    score_return_corr: float             = 0.0   # correlation: score vs 1M fwd return
    best_bucket:    str                  = ""
    worst_bucket:   str                  = ""
    raw_df:         Optional[pd.DataFrame] = field(default=None, repr=False)


@dataclass
class BacktestReport:
    """Aggregated backtest report across all tickers."""
    results:        list[BacktestResult]
    summary_df:     Optional[pd.DataFrame] = None
    overall_corr:   float = 0.0
    verdict:        str   = ""


class Backtester:
    """
    Runs a rolling historical backtest of the scoring system.

    For each ticker:
      - Uses a minimum lookback of 252 trading days (1 year) to compute indicators
      - Steps forward day by day, computing score and measuring forward returns
      - Aggregates statistics by score bucket

    Usage:
        bt      = Backtester(ticker_data_list, weights=None)
        report  = bt.run()
    """

    # Minimum bars needed before we can compute all indicators reliably
    MIN_LOOKBACK = 252

    # Step size — compute a new signal every N days (avoids overlap bias)
    STEP = 5   # weekly signals

    def __init__(self, ticker_data_list: list[TickerData],
                 weights: Optional[dict] = None) -> None:
        self.ticker_data_list = [td for td in ticker_data_list if td.is_valid]
        self.weights          = weights   # None = use default scoring

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self) -> BacktestReport:
        """Run backtest for all tickers and return an aggregated report."""
        results = []
        for td in self.ticker_data_list:
            result = self._backtest_one(td)
            if result:
                results.append(result)

        if not results:
            return BacktestReport(results=[], verdict="Insufficient data.")

        return self._build_report(results)

    # ── Per-ticker backtest ───────────────────────────────────────────────────

    def _backtest_one(self, td: TickerData) -> Optional[BacktestResult]:
        df = td.ohlcv.copy()
        if len(df) < self.MIN_LOOKBACK + 63:   # need 3 months of fwd data too
            return None

        records = []
        close   = df["close"]

        # Step through history, leaving 63 bars at the end for fwd returns
        for i in range(self.MIN_LOOKBACK, len(df) - 63, self.STEP):
            window = df.iloc[:i].copy()
            score  = self._compute_score(window, self.weights)
            if score is None:
                continue

            # Forward returns
            p0    = float(close.iloc[i])
            fwd1w = (float(close.iloc[min(i + 5,  len(df)-1)]) / p0 - 1) * 100
            fwd1m = (float(close.iloc[min(i + 21, len(df)-1)]) / p0 - 1) * 100
            fwd3m = (float(close.iloc[min(i + 63, len(df)-1)]) / p0 - 1) * 100

            records.append({
                "date":   df.index[i],
                "score":  score,
                "fwd1w":  fwd1w,
                "fwd1m":  fwd1m,
                "fwd3m":  fwd3m,
            })

        if not records:
            return None

        raw_df = pd.DataFrame(records)

        # Score vs return correlation
        corr = float(raw_df["score"].corr(raw_df["fwd1m"]))

        # Bucket statistics
        bucket_stats = self._compute_bucket_stats(raw_df)

        # Best / worst bucket by average 1M return
        sorted_b = sorted(bucket_stats, key=lambda b: b.avg_ret_1m, reverse=True)
        best     = sorted_b[0].label  if sorted_b else ""
        worst    = sorted_b[-1].label if sorted_b else ""

        return BacktestResult(
            ticker        = td.ticker,
            period        = td.period,
            total_signals = len(raw_df),
            bucket_stats  = bucket_stats,
            score_return_corr = corr,
            best_bucket   = best,
            worst_bucket  = worst,
            raw_df        = raw_df,
        )

    # ── Score computation (rolling window) ───────────────────────────────────

    def _compute_score(self, df: pd.DataFrame,
                       weights: Optional[dict]) -> Optional[float]:
        """Compute the opportunity score for the last bar of df."""
        try:
            close = df["close"]
            high  = df["high"]
            low   = df["low"]

            rsi     = float(RSIIndicator(close, window=RSI_WINDOW).rsi().iloc[-1])
            bb_pct  = float(BollingerBands(close, window=BB_WINDOW,
                                           window_dev=BB_STD).bollinger_pband().iloc[-1])
            sma50   = float(SMAIndicator(close, window=SMA_MID).sma_indicator().iloc[-1])
            sma200  = float(SMAIndicator(close, window=SMA_LONG).sma_indicator().iloc[-1])
            adx     = float(ADXIndicator(high, low, close,
                                         window=ADX_WINDOW).adx().iloc[-1])
            macd_h  = float(MACD(close).macd_diff().iloc[-1])
            stoch_k = float(StochasticOscillator(high, low, close,
                                                  window=STOCH_WINDOW).stoch().iloc[-1])
            price   = float(close.iloc[-1])

            if weights:
                return self._weighted_score(
                    rsi, bb_pct, price, sma50, sma200,
                    adx, macd_h, stoch_k, weights)
            else:
                return self._default_score(
                    rsi, bb_pct, price, sma50, sma200,
                    adx, macd_h, stoch_k)
        except Exception:
            return None

    @staticmethod
    def _default_score(rsi, bb_pct, price, sma50, sma200,
                       adx, macd_h, stoch_k) -> float:
        """Original hardcoded scoring logic."""
        score = 0
        if   rsi < 35: score += 10
        elif rsi < 50: score += 30
        elif rsi < 58: score += 25
        elif rsi < 68: score += 12

        score += max(0, min(20, int((1 - min(bb_pct, 1.2)) * 20)))
        score += 20 if price > sma50 else 0
        score += 15 if macd_h > 0 else 0

        if   adx > 30: score += 15
        elif adx > 25: score += 10
        elif adx > 20: score += 5

        if price > sma50 > sma200: score = min(100, score + 5)
        if stoch_k < 60:           score = min(100, score + 5)

        return float(min(100, score))

    @staticmethod
    def _weighted_score(rsi, bb_pct, price, sma50, sma200,
                        adx, macd_h, stoch_k, weights: dict) -> float:
        """Optimized scoring using data-derived weights (0-1 normalised features)."""
        # Normalise each feature to 0-1
        rsi_feat    = max(0.0, min(1.0, (80 - rsi) / 80))
        bb_feat     = max(0.0, min(1.0, 1 - bb_pct))
        sma_feat    = 1.0 if price > sma50 else 0.0
        macd_feat   = 1.0 if macd_h > 0 else 0.0
        adx_feat    = max(0.0, min(1.0, adx / 50))
        golden_feat = 1.0 if price > sma50 > sma200 else 0.0
        stoch_feat  = 1.0 if stoch_k < 60 else 0.0

        raw = (
            weights.get("rsi",    0.30) * rsi_feat  +
            weights.get("bb",     0.20) * bb_feat    +
            weights.get("sma50",  0.20) * sma_feat   +
            weights.get("macd",   0.15) * macd_feat  +
            weights.get("adx",    0.15) * adx_feat   +
            weights.get("golden", 0.05) * golden_feat +
            weights.get("stoch",  0.05) * stoch_feat
        )
        return float(min(100.0, raw * 100))

    # ── Bucket statistics ─────────────────────────────────────────────────────

    def _compute_bucket_stats(self,
                               raw_df: pd.DataFrame) -> list[BucketStats]:
        stats = []
        for lo, hi, label in BUCKETS:
            sub = raw_df[(raw_df["score"] >= lo) & (raw_df["score"] < hi)]
            if len(sub) == 0:
                stats.append(BucketStats(label=label))
                continue

            fwd1m = sub["fwd1m"]
            fwd3m = sub["fwd3m"]
            fwd1w = sub["fwd1w"]
            rf    = RISK_FREE_RATE / 12   # monthly risk-free

            sharpe = float(
                (fwd1m.mean() - rf) / fwd1m.std() * np.sqrt(12)
                if fwd1m.std() > 0 else 0.0
            )
            stats.append(BucketStats(
                label       = label,
                count       = len(sub),
                hit_rate_1m = float((fwd1m > 0).mean() * 100),
                hit_rate_3m = float((fwd3m > 0).mean() * 100),
                avg_ret_1m  = float(fwd1m.mean()),
                avg_ret_3m  = float(fwd3m.mean()),
                avg_ret_1w  = float(fwd1w.mean()),
                sharpe_1m   = sharpe,
            ))
        return stats

    # ── Report builder ────────────────────────────────────────────────────────

    def _build_report(self, results: list[BacktestResult]) -> BacktestReport:
        rows = []
        all_corrs = []
        for r in results:
            strong = next((b for b in r.bucket_stats
                           if "Strong" in b.label), None)
            rows.append({
                "Ticker":         r.ticker,
                "Signals":        r.total_signals,
                "Score-Ret Corr": f"{r.score_return_corr:+.3f}",
                "Strong Hit%1M":  f"{strong.hit_rate_1m:.0f}%" if strong else "N/A",
                "Strong Avg1M":   f"{strong.avg_ret_1m:+.1f}%" if strong else "N/A",
                "Strong Avg3M":   f"{strong.avg_ret_3m:+.1f}%" if strong else "N/A",
                "Sharpe(Strong)": f"{strong.sharpe_1m:.2f}"    if strong else "N/A",
                "Best Bucket":    r.best_bucket,
            })
            all_corrs.append(r.score_return_corr)

        summary_df   = pd.DataFrame(rows)
        overall_corr = float(np.mean(all_corrs)) if all_corrs else 0.0

        # Verdict
        if overall_corr > 0.15:
            verdict = ("✅  Strong predictive signal — score correlates positively "
                       "with forward returns. Weighting system is working.")
        elif overall_corr > 0.05:
            verdict = ("⚡  Moderate predictive signal — some correlation between "
                       "score and forward returns. Optimization may help.")
        else:
            verdict = ("⚠️  Weak predictive signal — limited correlation. "
                       "Consider optimizing weights with the WeightOptimizer.")

        return BacktestReport(
            results      = results,
            summary_df   = summary_df,
            overall_corr = overall_corr,
            verdict      = verdict,
        )
