"""
tests/test_strategies.py
─────────────────────────
Unit tests for Strategy subclasses and StrategyEngine.
"""

import pytest
from semisector.strategies import (
    Strategy,
    FullBuyStrategy, DCAStrategy, PullbackBuyStrategy,
    MomentumSwingStrategy, MeanReversionStrategy,
    ETFRotationStrategy, BasketStrategy, PairTradeStrategy,
    PartialTrimStrategy, StayFlatStrategy,
)
from semisector.strategy_engine import StrategyEngine


BUDGET = 10_000
ALL_CASH_CLASSES = [
    FullBuyStrategy, DCAStrategy, PullbackBuyStrategy,
    MomentumSwingStrategy, MeanReversionStrategy,
    ETFRotationStrategy, BasketStrategy, PairTradeStrategy,
    PartialTrimStrategy, StayFlatStrategy,
]


class TestStrategyInterface:
    """Every Strategy subclass must honour the abstract interface."""

    @pytest.mark.parametrize("cls", ALL_CASH_CLASSES)
    def test_is_strategy_subclass(self, cls, indicator_nvda):
        s = cls("NVDA", indicator_nvda, BUDGET)
        assert isinstance(s, Strategy)

    @pytest.mark.parametrize("cls", ALL_CASH_CLASSES)
    def test_name_is_non_empty_string(self, cls, indicator_nvda):
        s = cls("NVDA", indicator_nvda, BUDGET)
        assert isinstance(s.name, str) and len(s.name) > 0

    @pytest.mark.parametrize("cls", ALL_CASH_CLASSES)
    def test_action_is_non_empty_string(self, cls, indicator_nvda):
        s = cls("NVDA", indicator_nvda, BUDGET)
        assert isinstance(s.action, str) and len(s.action) > 0

    @pytest.mark.parametrize("cls", ALL_CASH_CLASSES)
    def test_rationale_is_non_empty_string(self, cls, indicator_nvda):
        s = cls("NVDA", indicator_nvda, BUDGET)
        assert isinstance(s.rationale, str) and len(s.rationale) > 0

    @pytest.mark.parametrize("cls", ALL_CASH_CLASSES)
    def test_tips_is_list_of_strings(self, cls, indicator_nvda):
        s = cls("NVDA", indicator_nvda, BUDGET)
        assert isinstance(s.tips, list)
        assert all(isinstance(t, str) for t in s.tips)

    @pytest.mark.parametrize("cls", ALL_CASH_CLASSES)
    def test_is_applicable_returns_bool(self, cls, indicator_nvda):
        s = cls("NVDA", indicator_nvda, BUDGET)
        assert isinstance(s.is_applicable(), bool)


class TestSharedHelpers:

    def test_stop_loss_below_price(self, indicator_nvda):
        s = FullBuyStrategy("NVDA", indicator_nvda, BUDGET)
        assert s.stop_loss < indicator_nvda.price

    def test_shares_positive(self, indicator_nvda):
        s = FullBuyStrategy("NVDA", indicator_nvda, BUDGET)
        assert s.shares >= 1

    def test_rr_ratio_string(self, indicator_nvda):
        s = FullBuyStrategy("NVDA", indicator_nvda, BUDGET)
        assert isinstance(s.rr_ratio, str)


class TestETFRotation:

    def test_not_applicable_for_etf_ticker(self, indicator_nvda):
        s = ETFRotationStrategy("SMH", indicator_nvda, BUDGET)
        assert not s.is_applicable()

    def test_applicable_for_stock_ticker(self, indicator_nvda):
        s = ETFRotationStrategy("NVDA", indicator_nvda, BUDGET)
        assert s.is_applicable()


class TestBasketStrategy:

    def test_applicable_for_basket_member(self, indicator_nvda):
        s = BasketStrategy("NVDA", indicator_nvda, BUDGET)
        assert s.is_applicable()

    def test_not_applicable_for_non_member(self, indicator_nvda):
        s = BasketStrategy("AMD", indicator_nvda, BUDGET)
        assert not s.is_applicable()


class TestStrategyEngine:

    def test_returns_non_empty_cash_list(self, ticker_data_nvda, indicator_nvda):
        engine = StrategyEngine(ticker_data_nvda, indicator_nvda,
                                BUDGET, show_options=False)
        cash, opt = engine.evaluate()
        assert len(cash) > 0
        assert opt is None   # options disabled

    def test_all_cash_items_are_strategy(self, ticker_data_nvda, indicator_nvda):
        engine = StrategyEngine(ticker_data_nvda, indicator_nvda,
                                BUDGET, show_options=False)
        cash, _ = engine.evaluate()
        assert all(isinstance(s, Strategy) for s in cash)

    def test_fallback_when_nothing_applies(self, ticker_data_nvda, indicator_nvda):
        """Force a situation where no standard strategy fires."""
        # Manually push score and rsi into the grey zone
        indicator_nvda.score   = 42
        indicator_nvda.rsi     = 55
        indicator_nvda.adx     = 10
        indicator_nvda.macd_hist = -0.1
        engine = StrategyEngine(ticker_data_nvda, indicator_nvda,
                                BUDGET, show_options=False)
        cash, _ = engine.evaluate()
        assert len(cash) >= 1   # fallback always present
