#!/usr/bin/env python3
"""
main.py
───────
Command-line entry point for the semisector analyzer.

Examples
────────
    # Full analysis (default)
    python main.py

    # Custom tickers / budget / period
    python main.py --tickers NVDA AMD MU --budget 25000 --period 6mo

    # Quick ranked table only
    python main.py --summary-only

    # Cash strategies only (faster — no options chain fetch)
    python main.py --no-options

    # Run backtest of scoring system
    python main.py --backtest

    # Optimize indicator weights then run analysis with optimized weights
    python main.py --optimize-weights

    # Send email report (reads credentials from .env file)
    python main.py --email recipient@outlook.com

    # Full automated daily run
    python main.py --optimize-weights --email you@outlook.com --no-options

    # Set up Windows Task Scheduler (4:30 PM Mon-Fri)
    python main.py --setup-schedule --email you@outlook.com

    # Remove scheduled task
    python main.py --remove-schedule

    # Save to custom database path
    python main.py --db data/my_runs.db

    # Disable database
    python main.py --no-db
"""

import argparse
import sys
from pathlib import Path

# ── dependency pre-check ──────────────────────────────────────────────────────
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

# ── project imports ───────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent

# Load .env file before importing modules that read env vars
from semisector.scheduler import load_env_file
load_env_file(PROJECT_ROOT)

from semisector.analyzer        import Analyzer
from semisector.backtester      import Backtester
from semisector.color_helper    import C
from semisector.config          import (
    DEFAULT_TICKERS, DEFAULT_PERIOD, DEFAULT_DB_PATH, DEFAULT_BUDGET
)
from semisector.email_reporter  import EmailReporter
from semisector.scheduler       import Scheduler
from semisector.ticker_data     import TickerData
from semisector.weight_optimizer import WeightOptimizer


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog        = "semisector",
        description = (
            "Semiconductor / Power / Memory Sector Opportunity Analyzer.\n"
            "Fetches live data, scores each ticker 0-100, suggests cash\n"
            "and options strategies, runs backtests, optimizes weights,\n"
            "sends daily email reports, and persists results to SQLite."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # ── Analysis args ─────────────────────────────────────────────────────────
    p.add_argument("--tickers",    nargs="+", default=DEFAULT_TICKERS,
                   metavar="TICKER")
    p.add_argument("--period",     default=DEFAULT_PERIOD,
                   help="yfinance history: 1mo 3mo 6mo 1y 2y  (default: %(default)s)")
    p.add_argument("--budget",     type=float, default=DEFAULT_BUDGET,
                   metavar="USD")
    p.add_argument("--summary-only", action="store_true")
    p.add_argument("--no-options",   action="store_true")

    # ── Database args ─────────────────────────────────────────────────────────
    p.add_argument("--db",    default=DEFAULT_DB_PATH, metavar="FILE")
    p.add_argument("--no-db", action="store_true")

    # ── Backtest ──────────────────────────────────────────────────────────────
    p.add_argument("--backtest", action="store_true",
                   help="Run historical backtest of scoring system")

    # ── Weight optimizer ──────────────────────────────────────────────────────
    p.add_argument("--optimize-weights", action="store_true",
                   help="Run Ridge + Random Forest optimization, apply best weights")

    # ── Email ─────────────────────────────────────────────────────────────────
    p.add_argument("--email", metavar="ADDRESS",
                   help="Send HTML report to this email address via Office 365")

    # ── Scheduler ─────────────────────────────────────────────────────────────
    p.add_argument("--setup-schedule",  action="store_true",
                   help="Create Windows Task Scheduler task (4:30 PM Mon-Fri)")
    p.add_argument("--remove-schedule", action="store_true",
                   help="Remove the Windows Scheduled Task")
    p.add_argument("--schedule-time",   default="16:30",
                   help="Time for scheduled task HH:MM (default: 16:30)")

    return p.parse_args()


def main() -> None:
    args = parse_args()

    # ── Scheduler commands (no analysis needed) ───────────────────────────────
    if args.setup_schedule:
        if not args.email:
            print(C.red("  ❌ --email is required when using --setup-schedule"))
            sys.exit(1)
        s = Scheduler(PROJECT_ROOT, args.email)
        s.setup(run_time=args.schedule_time)
        return

    if args.remove_schedule:
        s = Scheduler(PROJECT_ROOT, "")
        s.remove()
        return

    # ── Step 1: Weight optimization ───────────────────────────────────────────
    optimal_weights = None
    opt_result      = None

    if args.optimize_weights:
        print(f"\n{C.bold('═'*60)}")
        print(C.bold("  WEIGHT OPTIMIZATION"))
        print(C.bold("═"*60))
        print("  Fetching historical data for optimization...")

        # Use 2-year history for better training data
        td_list = []
        for ticker in args.tickers:
            print(f"  Loading {C.cyan(ticker):14s} ...", end=" ", flush=True)
            td = TickerData.fetch(ticker, "2y")
            if td.is_valid:
                td_list.append(td)
                print(C.green("✓"))
            else:
                print(C.red("SKIP"))

        if td_list:
            print("\n  Running Ridge Regression and Random Forest...")
            optimizer      = WeightOptimizer(td_list)
            opt_result     = optimizer.optimize()
            optimal_weights = opt_result.optimal_weights

            # Print comparison table
            print(f"\n  {C.bold('Model Comparison (Walk-Forward CV)')}")
            if opt_result.comparison_df is not None:
                from tabulate import tabulate
                print(tabulate(opt_result.comparison_df,
                               headers="keys", tablefmt="rounded_outline",
                               showindex=False))

            print(f"\n  🏆 Winner: {C.bold(opt_result.winner.name)}")
            print(f"  {opt_result.selection_reason}\n")

            print(f"  {C.bold('Optimal Weights:')}")
            for k, v in sorted(opt_result.optimal_weights.items(),
                                key=lambda x: x[1], reverse=True):
                bar = "█" * int(v * 30)
                print(f"    {k:<10} {bar:<30} {v*100:.1f}%")
        else:
            print(C.yellow("  ⚠  No valid data — using default weights."))

    # ── Step 2: Main analysis ─────────────────────────────────────────────────
    analyzer = Analyzer(
        tickers      = args.tickers,
        period       = args.period,
        budget       = args.budget,
        show_options = not args.no_options,
        db_path      = None if args.no_db else args.db,
        weights      = optimal_weights,
    )
    results = analyzer.run(summary_only=args.summary_only)

    if not results:
        sys.exit(1)

    # ── Step 3: Backtest ──────────────────────────────────────────────────────
    bt_report = None
    if args.backtest:
        print(f"\n{C.bold('═'*60)}")
        print(C.bold("  BACKTEST"))
        print(C.bold("═"*60))
        print("  Running rolling historical backtest...")
        print("  (uses 2-year history — this may take 1-2 minutes)\n")

        td_list = [r.td for r in results if r.td.is_valid]
        # Fetch 2y for backtest if current period is shorter
        if args.period not in ("2y",):
            bt_td_list = []
            for ticker in args.tickers:
                td = TickerData.fetch(ticker, "2y")
                if td.is_valid:
                    bt_td_list.append(td)
            td_list = bt_td_list

        backtester = Backtester(td_list, weights=optimal_weights)
        bt_report  = backtester.run()

        # Print results
        print(f"  Overall Score–Return Correlation: "
              f"{C.bold(f'{bt_report.overall_corr:+.3f}')}")
        print(f"  {bt_report.verdict}\n")

        if bt_report.summary_df is not None:
            from tabulate import tabulate
            print(tabulate(bt_report.summary_df,
                           headers="keys", tablefmt="rounded_outline",
                           showindex=False))

        # Detailed bucket stats for each ticker
        print(f"\n  {C.bold('Score Bucket Performance:')}")
        for r in bt_report.results:
            print(f"\n  {C.cyan(r.ticker)} — "
                  f"Corr: {r.score_return_corr:+.3f}  |  "
                  f"Best bucket: {r.best_bucket}")
            for b in r.bucket_stats:
                if b.count == 0:
                    continue
                print(f"    {b.label:<20} "
                      f"n={b.count:>4}  "
                      f"Hit%1M={b.hit_rate_1m:>5.1f}%  "
                      f"Avg1M={b.avg_ret_1m:>+6.1f}%  "
                      f"Avg3M={b.avg_ret_3m:>+6.1f}%  "
                      f"Sharpe={b.sharpe_1m:>+5.2f}")

    # ── Step 4: Email report ──────────────────────────────────────────────────
    if args.email:
        print(f"\n{C.bold('═'*60)}")
        print(C.bold("  SENDING EMAIL REPORT"))
        print(C.bold("═"*60))

        # Determine recipients
        env_to = __import__("os").getenv("SEMISECTOR_EMAIL_TO", "")
        to_list = [args.email]
        if env_to and env_to != args.email:
            to_list += [a.strip() for a in env_to.split(",")
                        if a.strip() and a.strip() != args.email]

        reporter = EmailReporter(to_addrs=to_list)
        reporter.send(results,
                      backtest_report=bt_report,
                      opt_result=opt_result)

        # Also save HTML preview to disk for GitHub upload
        html_path = PROJECT_ROOT / "reports" / \
            f"report_{__import__('datetime').date.today()}.html"
	html_path = PROJECT_ROOT / "reports" / \
    	    f"report_{__import__('datetime').date.today()}.html"
	    latest_path = PROJECT_ROOT / "reports" / "latest_report.html"
        html_path.parent.mkdir(exist_ok=True)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(reporter.preview_html(results, bt_report, opt_result))
	with open(html_path, "w", encoding="utf-8") as f:
    	    f.write(reporter.preview_html(results, bt_report, opt_result))
	with open(latest_path, "w", encoding="utf-8") as f:
            f.write(reporter.preview_html(results, bt_report, opt_result))
        print(C.dim(f"  📄 HTML report saved: {html_path}"))


if __name__ == "__main__":
    main()
