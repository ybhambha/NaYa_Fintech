#!/usr/bin/env python3
"""
main.py
───────
Command-line entry point for the semisector analyzer.

Examples
────────
    python main.py
    python main.py --tickers NVDA AMD MU
    python main.py --period 6mo --budget 25000
    python main.py --summary-only
    python main.py --no-options
    python main.py --db data/my_runs.db
    python main.py --no-db
"""

import argparse
import sys

# ── dependency pre-check (friendly message before any import fails) ───────────
REQUIRED = ["yfinance", "pandas", "numpy", "ta", "tabulate", "colorama"]
MISSING  = []
for pkg in REQUIRED:
    try:
        __import__(pkg)
    except ImportError:
        MISSING.append(pkg)

if MISSING:
    print(f"\n❌  Missing packages: {', '.join(MISSING)}")
    print("    Run:  pip install " + " ".join(MISSING))
    print("    Or:   pip install -r requirements.txt\n")
    sys.exit(1)

from semisector.analyzer import Analyzer
from semisector.config   import (
    DEFAULT_TICKERS, DEFAULT_PERIOD, DEFAULT_DB_PATH, DEFAULT_BUDGET
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="semisector",
        description=(
            "Semiconductor / Power / Memory Sector Opportunity Analyzer.\n"
            "Fetches live data, scores each ticker 0-100, suggests cash\n"
            "and options strategies, and persists results to SQLite."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--tickers", nargs="+", default=DEFAULT_TICKERS,
        metavar="TICKER",
        help="Space-separated ticker symbols  (default: %(default)s)",
    )
    p.add_argument(
        "--period", default=DEFAULT_PERIOD,
        help="yfinance history period: 1mo 3mo 6mo 1y 2y  (default: %(default)s)",
    )
    p.add_argument(
        "--budget", type=float, default=DEFAULT_BUDGET,
        metavar="USD",
        help="Capital to deploy per ticker in USD  (default: %(default)s)",
    )
    p.add_argument(
        "--summary-only", action="store_true",
        help="Print only the ranked table + sector verdict (skip per-ticker detail)",
    )
    p.add_argument(
        "--no-options", action="store_true",
        help="Skip options chain fetch — cash strategies only (faster)",
    )
    p.add_argument(
        "--db", default=DEFAULT_DB_PATH, metavar="FILE",
        help=f"SQLite database path  (default: %(default)s)",
    )
    p.add_argument(
        "--no-db", action="store_true",
        help="Disable SQLite persistence entirely",
    )
    return p.parse_args()


def main() -> None:
    args     = parse_args()
    analyzer = Analyzer(
        tickers      = args.tickers,
        period       = args.period,
        budget       = args.budget,
        show_options = not args.no_options,
        db_path      = None if args.no_db else args.db,
    )
    analyzer.run(summary_only=args.summary_only)


if __name__ == "__main__":
    main()
