"""
semisector — Semiconductor / Power / Memory Sector Opportunity Analyzer
"""

from semisector.config          import DEFAULT_TICKERS, DEFAULT_PERIOD, DEFAULT_DB_PATH
from semisector.ticker_data     import TickerData
from semisector.indicators      import IndicatorEngine
from semisector.strategies      import Strategy, OptionsSnapshot, OptionsStrategy
from semisector.strategy_engine import StrategyEngine
from semisector.models          import AnalysisResult
from semisector.reporter        import Reporter
from semisector.database        import DatabaseManager
from semisector.analyzer        import Analyzer

__version__ = "1.0.0"
__all__ = [
    "Analyzer", "AnalysisResult",
    "TickerData", "IndicatorEngine",
    "Strategy", "StrategyEngine",
    "OptionsSnapshot", "OptionsStrategy",
    "Reporter", "DatabaseManager",
    "DEFAULT_TICKERS", "DEFAULT_PERIOD", "DEFAULT_DB_PATH",
]
