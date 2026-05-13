"""
semisector/strategy_engine.py
──────────────────────────────
StrategyEngine — evaluates every strategy class against current
indicators and returns only the applicable ones in priority order.
"""

from __future__ import annotations

from typing import Optional

from semisector.indicators import IndicatorEngine
from semisector.ticker_data import TickerData
from semisector.strategies import (
    Strategy,
    FullBuyStrategy, DCAStrategy, PullbackBuyStrategy,
    MomentumSwingStrategy, MeanReversionStrategy,
    ETFRotationStrategy, BasketStrategy, PairTradeStrategy,
    PartialTrimStrategy, StayFlatStrategy,
    OptionsSnapshot, OptionsStrategy,
)


class StrategyEngine:
    """
    Instantiates every registered CashStrategy subclass in priority order,
    calls is_applicable() on each, and returns a (cash_list, options) tuple.

    Adding a new strategy:
        1. Write a new Strategy subclass in strategies.py
        2. Add it to CASH_CLASSES below — order determines display priority.
        Nothing else needs to change.
    """

    # Ordered priority list — first match shown first in reports
    CASH_CLASSES: list[type[Strategy]] = [
        FullBuyStrategy,
        DCAStrategy,
        PullbackBuyStrategy,
        MomentumSwingStrategy,
        MeanReversionStrategy,
        ETFRotationStrategy,
        BasketStrategy,
        PairTradeStrategy,
        PartialTrimStrategy,
        StayFlatStrategy,
    ]

    def __init__(self, td: TickerData, ind: IndicatorEngine,
                 budget: float, show_options: bool) -> None:
        self.td           = td
        self.ind          = ind
        self.budget       = budget
        self.show_options = show_options

    def evaluate(self) -> tuple[list[Strategy], Optional[OptionsStrategy]]:
        """
        Returns (cash_strategies, options_strategy).

        cash_strategies — non-empty list; falls back to MonitorStrategy
                          if nothing else applies.
        options_strategy — None when show_options=False or no chain available.
        """
        cash: list[Strategy] = [
            cls(self.td.ticker, self.ind, self.budget)
            for cls in self.CASH_CLASSES
            if cls(self.td.ticker, self.ind, self.budget).is_applicable()
        ]

        if not cash:
            cash = [self._monitor_strategy()]

        opt: Optional[OptionsStrategy] = None
        if self.show_options:
            snap = OptionsSnapshot.fetch(self.td.ticker, self.ind.price)
            opt  = OptionsStrategy(self.td.ticker, self.ind,
                                   self.budget, snap)

        return cash, opt

    # ── Fallback ──────────────────────────────────────────────────────────────

    def _monitor_strategy(self) -> Strategy:
        """Returns an inline monitor-only strategy when no others apply."""

        ticker = self.td.ticker
        ind    = self.ind
        budget = self.budget

        class _Monitor(Strategy):
            @property
            def name(self):      return "📊 Monitor — No Clear Edge Right Now"
            @property
            def action(self):    return (f"Hold off on {self.ticker}. "
                                         "Revisit when score > 55 or RSI resets below 50.")
            @property
            def rationale(self): return (f"Score {self.ind.score}/100, "
                                         f"RSI {self.ind.rsi:.0f} — no strong signal.")
            @property
            def tips(self):      return [
                "Set a weekly reminder to re-run this analysis.",
                "Watch for a MACD bullish crossover as a fresh entry trigger.",
            ]
            def is_applicable(self): return True

        return _Monitor(ticker, ind, budget)
