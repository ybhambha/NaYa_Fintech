"""
tests/conftest.py
─────────────────
Shared pytest fixtures.  All tests that need a TickerData or
IndicatorEngine import from here — no network calls in the test suite.
"""

import numpy as np
import pandas as pd
import pytest

from semisector.ticker_data import TickerData
from semisector.indicators  import IndicatorEngine


def _make_ohlcv(seed: int = 42, n: int = 260,
                drift: float = 0.001) -> pd.DataFrame:
    """Return a synthetic OHLCV DataFrame suitable for IndicatorEngine."""
    np.random.seed(seed)
    close  = 100 * np.cumprod(1 + np.random.normal(drift, 0.018, n))
    high   = close * (1 + np.abs(np.random.normal(0, 0.008, n)))
    low    = close * (1 - np.abs(np.random.normal(0, 0.008, n)))
    volume = np.random.randint(5_000_000, 20_000_000, n).astype(float)
    return pd.DataFrame(
        {"close": close, "high": high, "low": low,
         "open": close,  "volume": volume}
    )


@pytest.fixture
def sample_ohlcv():
    return _make_ohlcv()


@pytest.fixture
def ticker_data_nvda():
    df = _make_ohlcv(seed=42)
    return TickerData(
        ticker="NVDA", period="1y", ohlcv=df,
        short_name="NVIDIA Corp",
        pe_fwd=28.0, peg=1.5, rev_growth=0.42,
        market_cap=2e12, beta=1.6,
    )


@pytest.fixture
def ticker_data_mu():
    df = _make_ohlcv(seed=7, drift=0.0005)
    return TickerData(
        ticker="MU", period="1y", ohlcv=df,
        short_name="Micron Technology",
        pe_fwd=14.0, peg=0.8, rev_growth=0.28,
        market_cap=120e9, beta=1.3,
    )


@pytest.fixture
def indicator_nvda(ticker_data_nvda):
    return IndicatorEngine(ticker_data_nvda)


@pytest.fixture
def indicator_mu(ticker_data_mu):
    return IndicatorEngine(ticker_data_mu)
