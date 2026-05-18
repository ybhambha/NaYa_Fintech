"""
semisector/analyzer.py
───────────────────────
Analyzer — top-level orchestrator that wires together all classes
in the pipeline:

    TickerData  →  IndicatorEngine  →  StrategyEngine  →  AnalysisResult
                                                        →  Reporter
                                                        →  DatabaseManager
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from semisector.color_helper    import C
from semisector.config          import BENCH_TICKER, DEFAULT_DB_PATH
from semisector.database        import DatabaseManager
from semisector.indicators      import IndicatorEngine
from semisector.models          import AnalysisResult
from semisector.reporter        import Reporter
from semisector.strategy_engine import StrategyEngine
from semisector.ticker_data     import TickerData


class Analyzer:
    """
    Orchestrates the full analysis pipeline for a list of tickers.

    Usage:
        analyzer = Analyzer(tickers=["NVDA","AMD"], period="1y",
                            budget=10_000, show_options=False)
        analyzer.run()
    """

    def __init__(
        self,
        tickers:      list[str],
        period:       str,
        budget:       float,
        show_options: bool,
        db_path:      Optional[str]  = DEFAULT_DB_PATH,
        weights:      Optional[dict] = None,
    ) -> None:
        self.tickers      = tickers
        self.period       = period
        self.budget       = budget
        self.show_options = show_options
        self.db_path      = db_path
        self.weights      = weights    # None = default scoring weights
        self.reporter     = Reporter()

    # ── Public entry point ────────────────────────────────────────────────────

    def run(self, summary_only: bool = False) -> list[AnalysisResult]:
        """
        Run the full pipeline:
          1. Fetch & analyse all tickers
          2. Print summary table
          3. Print per-ticker detail reports (unless summary_only)
          4. Print sector verdict
          5. Save to SQLite (unless db_path is None)

        Returns the list of AnalysisResult objects for programmatic use.
        """
        self._print_header()
        spy_ret = self._fetch_benchmark()
        results = self._analyse_all(spy_ret)

        if not results:
            print(C.red("\nNo data retrieved. "
                        "Check ticker symbols / internet connection.\n"))
            sys.exit(1)

        self.reporter.print_summary_table(results)
        if not summary_only:
            self.reporter.print_detail_reports(results, self.show_options)
        self.reporter.print_sector_verdict(results)

        if self.db_path:
            self._save_to_db(results)

        return results

    # ── Private helpers ───────────────────────────────────────────────────────

    def _print_header(self) -> None:
        print(f"\n{C.bold('═' * 72)}")
        print(C.bold(
            f"  SEMICONDUCTOR SECTOR ANALYSIS  |  {datetime.today():%Y-%m-%d}"))
        print(C.bold("═" * 72))
        print(f"  Period: {self.period}   |   Budget: ${self.budget:,.0f}   |   "
              f"Options: {'ON' if self.show_options else 'OFF (cash only)'}")
        print(f"  Tickers: {', '.join(self.tickers)}")
        print(C.bold("─" * 72))

    def _fetch_benchmark(self) -> Optional[float]:
        """Return SPY 3-month return for relative-strength calculations."""
        df = TickerData.fetch(BENCH_TICKER, self.period).ohlcv
        if df is None:
            return None
        p0 = float(df.iloc[max(0, len(df) - 63)]["close"])
        px = float(df.iloc[-1]["close"])
        return (px / p0 - 1) * 100

    def _analyse_one(self, ticker: str,
                     spy_ret: Optional[float]) -> Optional[AnalysisResult]:
        """Full pipeline for a single ticker. Returns None on failure."""
        print(f"  Fetching {C.cyan(ticker):14s} ...", end=" ", flush=True)
        td = TickerData.fetch(ticker, self.period)
        if not td.is_valid:
            print(C.red("SKIP"))
            return None

        try:
            ind = IndicatorEngine(td)
        except ValueError as e:
            print(C.red(f"SKIP ({e})"))
            return None

        rs = ((ind.ret_3m or 0) - spy_ret) if spy_ret is not None else None

        engine = StrategyEngine(td, ind, self.budget, self.show_options)
        cash_strats, opt_strat = engine.evaluate()

        print(C.green("✓"))
        return AnalysisResult(
            td=td, ind=ind,
            cash_strats=cash_strats, opt_strat=opt_strat,
            rs_vs_spy=rs,
        )

    def _analyse_all(self,
                     spy_ret: Optional[float]) -> list[AnalysisResult]:
        results = []
        for ticker in self.tickers:
            result = self._analyse_one(ticker, spy_ret)
            if result:
                results.append(result)
        return results

    def _save_to_db(self, results: list[AnalysisResult]) -> None:
        """Persist the full run to SQLite via DatabaseManager."""
        print()
        try:
            with DatabaseManager(self.db_path) as db:
                run_id = db.save_run(
                    self.period, self.budget, self.tickers)
                for result in results:
                    db.save_result(run_id, result)
                total_rows = sum(
                    len(r.td.ohlcv)
                    for r in results if r.td.ohlcv is not None
                )
                print(C.green(
                    f"  ✅ Saved run #{run_id} — "
                    f"{len(results)} tickers, "
                    f"{total_rows:,} OHLCV rows, "
                    f"{sum(len(r.cash_strats) for r in results)} strategies "
                    f"→ {Path(self.db_path).resolve()}"
                ))
        except Exception as e:
            print(C.red(f"  ⚠  Database save failed: {e}"))
