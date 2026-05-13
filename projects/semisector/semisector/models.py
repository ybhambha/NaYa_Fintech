"""
semisector/models.py
─────────────────────
AnalysisResult — lightweight dataclass that aggregates TickerData,
IndicatorEngine outputs, and generated strategies into one clean
object that is passed between the Analyzer, Reporter, and DatabaseManager.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from semisector.ticker_data import TickerData
from semisector.indicators  import IndicatorEngine
from semisector.strategies  import Strategy, OptionsStrategy


@dataclass
class AnalysisResult:
    """
    Fully-analysed snapshot for one ticker.
    Created by Analyzer — never constructed directly by callers.
    """

    td:          TickerData
    ind:         IndicatorEngine
    cash_strats: list[Strategy]
    opt_strat:   Optional[OptionsStrategy]
    rs_vs_spy:   Optional[float] = None   # relative strength vs SPY (3-month)

    # ── Convenience pass-throughs ─────────────────────────────────────────────

    @property
    def ticker(self) -> str:
        return self.td.ticker

    @property
    def name(self) -> str:
        return self.td.short_name or self.td.ticker

    @property
    def score(self) -> float:
        return self.ind.score

    @property
    def price(self) -> float:
        return self.ind.price
