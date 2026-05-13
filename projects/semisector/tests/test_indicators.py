"""
tests/test_indicators.py
─────────────────────────
Unit tests for IndicatorEngine.
"""

import pytest
from semisector.ticker_data import TickerData
from semisector.indicators  import IndicatorEngine


class TestIndicatorEngine:

    def test_basic_attributes_exist(self, indicator_nvda):
        ind = indicator_nvda
        for attr in ("price", "rsi", "macd_hist", "adx", "atr",
                     "sma50", "sma200", "bb_pct", "stoch_k", "vwap",
                     "vol_30d_ann", "max_dd", "score", "trend"):
            assert hasattr(ind, attr), f"Missing attribute: {attr}"

    def test_score_in_range(self, indicator_nvda):
        assert 0 <= indicator_nvda.score <= 100

    def test_rsi_in_range(self, indicator_nvda):
        assert 0 <= indicator_nvda.rsi <= 100

    def test_price_positive(self, indicator_nvda):
        assert indicator_nvda.price > 0

    def test_score_detail_is_dict(self, indicator_nvda):
        assert isinstance(indicator_nvda.score_detail, dict)
        assert len(indicator_nvda.score_detail) > 0

    def test_trend_is_string(self, indicator_nvda):
        assert isinstance(indicator_nvda.trend, str)
        assert len(indicator_nvda.trend) > 0

    def test_returns_are_floats_or_none(self, indicator_nvda):
        for attr in ("ret_1w", "ret_1m", "ret_3m", "ret_6m", "ret_1y"):
            v = getattr(indicator_nvda, attr)
            assert v is None or isinstance(v, float)

    def test_max_dd_non_positive(self, indicator_nvda):
        assert indicator_nvda.max_dd <= 0

    def test_vol_positive(self, indicator_nvda):
        assert indicator_nvda.vol_30d_ann > 0

    def test_golden_cross_boolean(self, indicator_nvda):
        assert isinstance(indicator_nvda.golden_cross, bool)

    def test_raises_on_invalid_data(self):
        td = TickerData(ticker="BAD", period="1y", ohlcv=None)
        with pytest.raises(ValueError):
            IndicatorEngine(td)

    def test_support_below_resistance(self, indicator_nvda):
        assert indicator_nvda.support < indicator_nvda.resistance
