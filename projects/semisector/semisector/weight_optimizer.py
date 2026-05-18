"""
semisector/weight_optimizer.py
───────────────────────────────
WeightOptimizer — uses Ridge Regression and Random Forest to find
statistically optimal indicator weights for the scoring system.

Pipeline
────────
1. Build a feature matrix from historical indicator values
2. Target variable = 1-month forward return (next 21 trading days)
3. Train Ridge Regression and Random Forest with walk-forward CV
4. Compare both models on out-of-sample R², RMSE, and direction accuracy
5. Select the better model automatically
6. Return normalised weights dict compatible with Backtester + IndicatorEngine

Walk-forward validation
───────────────────────
Rather than a simple train/test split, we use expanding-window
walk-forward validation (standard in finance) to avoid look-ahead bias:
  - Train on first 60% of data
  - Test on next 10%
  - Expand window, repeat 3 times
  - Average out-of-sample scores
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
from ta.volatility import BollingerBands

from semisector.config      import (
    RSI_WINDOW, BB_WINDOW, BB_STD, ADX_WINDOW, STOCH_WINDOW,
    SMA_MID, SMA_LONG,
)
from semisector.ticker_data import TickerData


# ── Feature names (must match _build_features) ───────────────────────────────
FEATURE_NAMES = ["rsi_feat", "bb_feat", "sma_feat",
                 "macd_feat", "adx_feat", "golden_feat", "stoch_feat"]

WEIGHT_KEYS   = ["rsi", "bb", "sma50", "macd", "adx", "golden", "stoch"]


@dataclass
class ModelResult:
    """Results for one model (Ridge or Random Forest)."""
    name:           str
    weights:        dict[str, float]
    r2_oos:         float    # out-of-sample R²
    rmse_oos:       float    # out-of-sample RMSE
    dir_accuracy:   float    # % correct direction predictions
    feature_importance: dict[str, float] = field(default_factory=dict)


@dataclass
class OptimizationResult:
    """Full optimization output comparing both models."""
    ridge:          ModelResult
    random_forest:  ModelResult
    winner:         ModelResult          # automatically selected better model
    optimal_weights: dict[str, float]   # weights to use in scoring
    selection_reason: str
    comparison_df:  Optional[pd.DataFrame] = None


class WeightOptimizer:
    """
    Fits Ridge Regression and Random Forest to historical indicator data
    to find optimal scoring weights.

    Usage:
        optimizer = WeightOptimizer(ticker_data_list)
        result    = optimizer.optimize()
        print(result.optimal_weights)
        print(result.winner.name)
    """

    MIN_SAMPLES = 100   # minimum data points needed to fit models

    def __init__(self, ticker_data_list: list[TickerData]) -> None:
        self.ticker_data_list = [td for td in ticker_data_list if td.is_valid]

    # ── Public API ────────────────────────────────────────────────────────────

    def optimize(self) -> OptimizationResult:
        """
        Build feature matrix, train both models with walk-forward CV,
        compare them, and return the winner with optimal weights.
        """
        # Build combined feature matrix across all tickers
        X, y = self._build_feature_matrix()

        if len(X) < self.MIN_SAMPLES:
            return self._fallback_result(
                f"Insufficient data ({len(X)} samples, need {self.MIN_SAMPLES})")

        # Walk-forward cross-validation
        ridge_scores, rf_scores = [], []
        ridge_weights_list, rf_weights_list = [], []
        ridge_importances, rf_importances   = [], []

        folds = self._walk_forward_folds(len(X))
        for train_idx, test_idx in folds:
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            # Ridge
            rr = self._fit_ridge(X_train, y_train, X_test, y_test)
            ridge_scores.append(rr)
            ridge_weights_list.append(rr["weights"])
            ridge_importances.append(rr["importances"])

            # Random Forest
            rf = self._fit_rf(X_train, y_train, X_test, y_test)
            rf_scores.append(rf)
            rf_weights_list.append(rf["weights"])
            rf_importances.append(rf["importances"])

        # Average weights across folds
        ridge_w  = self._average_weights(ridge_weights_list)
        rf_w     = self._average_weights(rf_weights_list)
        ridge_fi = self._average_weights(ridge_importances)
        rf_fi    = self._average_weights(rf_importances)

        # Average OOS metrics
        def avg(scores, key): return float(np.mean([s[key] for s in scores]))

        ridge_result = ModelResult(
            name               = "Ridge Regression",
            weights            = ridge_w,
            r2_oos             = avg(ridge_scores, "r2"),
            rmse_oos           = avg(ridge_scores, "rmse"),
            dir_accuracy       = avg(ridge_scores, "dir_acc"),
            feature_importance = ridge_fi,
        )
        rf_result = ModelResult(
            name               = "Random Forest",
            weights            = rf_w,
            r2_oos             = avg(rf_scores, "r2"),
            rmse_oos           = avg(rf_scores, "rmse"),
            dir_accuracy       = avg(rf_scores, "dir_acc"),
            feature_importance = rf_fi,
        )

        # Select winner
        winner, reason = self._select_winner(ridge_result, rf_result)

        # Comparison table
        comparison_df = pd.DataFrame([
            {"Model": "Ridge Regression",
             "R² (OOS)":       f"{ridge_result.r2_oos:.4f}",
             "RMSE (OOS)":     f"{ridge_result.rmse_oos:.4f}",
             "Dir Accuracy":   f"{ridge_result.dir_accuracy:.1f}%",
             "Selected":       "✅" if winner.name == "Ridge Regression" else ""},
            {"Model": "Random Forest",
             "R² (OOS)":       f"{rf_result.r2_oos:.4f}",
             "RMSE (OOS)":     f"{rf_result.rmse_oos:.4f}",
             "Dir Accuracy":   f"{rf_result.dir_accuracy:.1f}%",
             "Selected":       "✅" if winner.name == "Random Forest" else ""},
        ])

        return OptimizationResult(
            ridge            = ridge_result,
            random_forest    = rf_result,
            winner           = winner,
            optimal_weights  = winner.weights,
            selection_reason = reason,
            comparison_df    = comparison_df,
        )

    # ── Feature matrix ────────────────────────────────────────────────────────

    def _build_feature_matrix(self) -> tuple[np.ndarray, np.ndarray]:
        """Build (X, y) across all tickers with walk-forward features."""
        all_X, all_y = [], []

        for td in self.ticker_data_list:
            df    = td.ohlcv.copy()
            close = df["close"]
            high  = df["high"]
            low   = df["low"]

            # Compute indicator series
            rsi    = RSIIndicator(close, window=RSI_WINDOW).rsi()
            bb_pct = BollingerBands(close, window=BB_WINDOW,
                                    window_dev=BB_STD).bollinger_pband()
            sma50  = SMAIndicator(close, window=SMA_MID).sma_indicator()
            sma200 = SMAIndicator(close, window=SMA_LONG).sma_indicator()
            adx    = ADXIndicator(high, low, close,
                                  window=ADX_WINDOW).adx()
            macd_h = MACD(close).macd_diff()
            stoch  = StochasticOscillator(high, low, close,
                                          window=STOCH_WINDOW).stoch()

            # Forward 1-month return (target)
            fwd_ret = close.pct_change(21).shift(-21) * 100

            # Build feature rows (skip NaN warm-up period)
            for i in range(250, len(df) - 21):
                try:
                    p     = float(close.iloc[i])
                    s50   = float(sma50.iloc[i])
                    s200  = float(sma200.iloc[i])
                    r     = float(rsi.iloc[i])
                    bb    = float(bb_pct.iloc[i])
                    a     = float(adx.iloc[i])
                    mh    = float(macd_h.iloc[i])
                    sk    = float(stoch.iloc[i])
                    fwd   = float(fwd_ret.iloc[i])

                    if any(np.isnan(v) for v in [r, bb, s50, s200, a, mh, sk, fwd]):
                        continue

                    # Normalise features to 0–1
                    row = [
                        max(0.0, min(1.0, (80 - r) / 80)),      # rsi_feat
                        max(0.0, min(1.0, 1 - bb)),              # bb_feat
                        1.0 if p > s50 else 0.0,                 # sma_feat
                        1.0 if mh > 0 else 0.0,                  # macd_feat
                        max(0.0, min(1.0, a / 50)),              # adx_feat
                        1.0 if p > s50 > s200 else 0.0,          # golden_feat
                        1.0 if sk < 60 else 0.0,                 # stoch_feat
                    ]
                    all_X.append(row)
                    all_y.append(fwd)
                except Exception:
                    continue

        if not all_X:
            return np.array([]), np.array([])

        return np.array(all_X), np.array(all_y)

    # ── Walk-forward folds ────────────────────────────────────────────────────

    def _walk_forward_folds(self, n: int,
                             n_folds: int = 3) -> list[tuple]:
        """
        Expanding window walk-forward folds.
        Returns list of (train_indices, test_indices) tuples.
        """
        folds    = []
        fold_size = n // (n_folds + 1)
        for i in range(n_folds):
            train_end  = fold_size * (i + 2)
            test_start = train_end
            test_end   = min(train_end + fold_size, n)
            if test_end > test_start:
                folds.append((
                    np.arange(0, train_end),
                    np.arange(test_start, test_end),
                ))
        return folds

    # ── Model fitting ─────────────────────────────────────────────────────────

    def _fit_ridge(self, X_train, y_train,
                   X_test,  y_test) -> dict:
        """Fit Ridge Regression and return OOS metrics + weights."""
        from sklearn.linear_model import RidgeCV
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import r2_score, mean_squared_error

        scaler  = StandardScaler()
        Xs_train = scaler.fit_transform(X_train)
        Xs_test  = scaler.transform(X_test)

        model   = RidgeCV(alphas=[0.01, 0.1, 1.0, 10.0, 100.0], cv=5)
        model.fit(Xs_train, y_train)
        y_pred  = model.predict(Xs_test)

        # Convert coefficients to positive weights (normalised 0–1)
        coefs   = model.coef_
        weights = self._coefs_to_weights(coefs)

        # Feature importance = absolute scaled coefficients
        abs_c   = np.abs(coefs)
        fi      = dict(zip(WEIGHT_KEYS,
                           (abs_c / abs_c.sum() if abs_c.sum() > 0
                            else abs_c).tolist()))

        return {
            "r2":          float(r2_score(y_test, y_pred)),
            "rmse":        float(np.sqrt(mean_squared_error(y_test, y_pred))),
            "dir_acc":     float(np.mean(np.sign(y_pred) == np.sign(y_test)) * 100),
            "weights":     weights,
            "importances": fi,
        }

    def _fit_rf(self, X_train, y_train,
                X_test,  y_test) -> dict:
        """Fit Random Forest Regressor and return OOS metrics + weights."""
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.metrics  import r2_score, mean_squared_error

        model = RandomForestRegressor(
            n_estimators = 200,
            max_depth    = 4,       # shallow to prevent overfit
            min_samples_leaf = 20,
            random_state = 42,
            n_jobs       = -1,
        )
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        # Feature importances (already 0–1 summing to 1)
        fi     = dict(zip(WEIGHT_KEYS,
                          model.feature_importances_.tolist()))

        # Convert importances to weights
        weights = {k: float(v) for k, v in fi.items()}

        return {
            "r2":          float(r2_score(y_test, y_pred)),
            "rmse":        float(np.sqrt(mean_squared_error(y_test, y_pred))),
            "dir_acc":     float(np.mean(np.sign(y_pred) == np.sign(y_test)) * 100),
            "weights":     weights,
            "importances": fi,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _coefs_to_weights(coefs: np.ndarray) -> dict[str, float]:
        """
        Convert Ridge coefficients to positive normalised weights.
        Negative coefficients are floored to 0 (a negative RSI weight
        would mean 'buy when overbought' — counter-intuitive).
        """
        pos    = np.maximum(coefs, 0)
        total  = pos.sum()
        normed = pos / total if total > 0 else np.ones(len(pos)) / len(pos)
        return dict(zip(WEIGHT_KEYS, normed.tolist()))

    @staticmethod
    def _average_weights(weight_list: list[dict]) -> dict[str, float]:
        """Average a list of weight dicts across folds."""
        if not weight_list:
            return {k: 1/len(WEIGHT_KEYS) for k in WEIGHT_KEYS}
        avg = {}
        for key in WEIGHT_KEYS:
            avg[key] = float(np.mean([w.get(key, 0) for w in weight_list]))
        # Re-normalise so weights sum to 1
        total = sum(avg.values())
        return {k: v / total for k, v in avg.items()} if total > 0 else avg

    @staticmethod
    def _select_winner(ridge: ModelResult,
                       rf: ModelResult) -> tuple[ModelResult, str]:
        """
        Select the better model based on a composite score:
          40% R² weight + 30% direction accuracy + 30% inverse RMSE
        """
        def safe_r2(m):  return max(0.0, m.r2_oos)
        def safe_dir(m): return m.dir_accuracy / 100
        def safe_rmse(m): return 1 / (1 + m.rmse_oos)

        r_score = 0.4*safe_r2(ridge) + 0.3*safe_dir(ridge) + 0.3*safe_rmse(ridge)
        f_score = 0.4*safe_r2(rf)    + 0.3*safe_dir(rf)    + 0.3*safe_rmse(rf)

        if f_score >= r_score:
            reason = (
                f"Random Forest selected (composite score {f_score:.4f} vs "
                f"Ridge {r_score:.4f}). "
                f"RF R²={rf.r2_oos:.4f}, Dir={rf.dir_accuracy:.1f}%, "
                f"RMSE={rf.rmse_oos:.4f}."
            )
            return rf, reason
        else:
            reason = (
                f"Ridge Regression selected (composite score {r_score:.4f} vs "
                f"RF {f_score:.4f}). "
                f"Ridge R²={ridge.r2_oos:.4f}, Dir={ridge.dir_accuracy:.1f}%, "
                f"RMSE={ridge.rmse_oos:.4f}."
            )
            return ridge, reason

    def _fallback_result(self, reason: str) -> OptimizationResult:
        """Return default weights when there's insufficient data."""
        default = {"rsi": 0.30, "bb": 0.20, "sma50": 0.20,
                   "macd": 0.15, "adx": 0.15, "golden": 0.05, "stoch": 0.05}
        dummy = ModelResult(name="Default (fallback)", weights=default,
                            r2_oos=0.0, rmse_oos=0.0, dir_accuracy=0.0)
        return OptimizationResult(
            ridge=dummy, random_forest=dummy, winner=dummy,
            optimal_weights=default, selection_reason=reason)
