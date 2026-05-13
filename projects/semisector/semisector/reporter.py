"""
semisector/reporter.py
───────────────────────
Reporter — all console output lives here and nowhere else.
Has zero business logic; its only job is formatting and printing
AnalysisResult objects.
"""

from __future__ import annotations

from typing import Optional

from tabulate import tabulate

from semisector.color_helper import C
from semisector.config       import SCORE_HIGH
from semisector.models       import AnalysisResult


class Reporter:
    """
    Formats and prints:
      - Ranked summary table
      - Per-ticker detail reports (technicals, returns, risk,
        fundamentals, cash strategies, options)
      - Sector-level verdict
    """

    W = 72   # console line width

    # ── Public API ────────────────────────────────────────────────────────────

    def print_summary_table(self, results: list[AnalysisResult]) -> None:
        sr = sorted(results, key=lambda r: r.score, reverse=True)
        headers = [
            "Rank", "Ticker", "Price", "Score", "RSI", "BB%", "ADX",
            "Vol30d", "1M", "3M", "vs SPY", "Fwd P/E", "PEG",
            "Top Cash Strategy",
        ]
        rows = []
        for i, r in enumerate(sr, 1):
            top = r.cash_strats[0].name if r.cash_strats else "—"
            rs  = r.rs_vs_spy
            rows.append([
                i,
                C.bold(r.ticker),
                f"${r.price:,.2f}",
                C.score(r.score),
                f"{r.ind.rsi:.1f}",
                f"{r.ind.bb_pct*100:.0f}%",
                f"{r.ind.adx:.1f}",
                f"{r.ind.vol_30d_ann:.0f}%",
                C.pct(r.ind.ret_1m),
                C.pct(r.ind.ret_3m),
                C.pct(rs) if rs is not None else C.dim("N/A"),
                C.ratio(r.td.pe_fwd),
                C.ratio(r.td.peg),
                top[:38],
            ])
        print(f"\n{C.bold('━' * self.W)}")
        print(C.bold("  RANKED OPPORTUNITY TABLE  (sorted by opportunity score)"))
        print(C.bold("━" * self.W))
        print(tabulate(rows, headers=headers, tablefmt="rounded_outline"))

    def print_detail_reports(self, results: list[AnalysisResult],
                             show_options: bool) -> None:
        for r in sorted(results, key=lambda x: x.score, reverse=True):
            self._print_one(r, show_options)

    def print_sector_verdict(self, results: list[AnalysisResult]) -> None:
        avg_score  = sum(r.score           for r in results) / len(results)
        avg_rsi    = sum(r.ind.rsi         for r in results) / len(results)
        avg_vol    = sum(r.ind.vol_30d_ann for r in results) / len(results)
        high_opp   = [r.ticker for r in results if r.score >= SCORE_HIGH]
        overbought = [r.ticker for r in results if r.ind.rsi > 68]
        top        = max(results, key=lambda x: x.score)

        print(f"\n{'═' * self.W}")
        print(C.bold("  SECTOR-LEVEL VERDICT  &  HAVE I MISSED THE BOAT?"))
        print(f"{'─' * self.W}")
        print(f"  Average opportunity score : {C.score(avg_score)}")
        print(f"  Average RSI               : {avg_rsi:.1f}")
        print(f"  Average annualised vol    : {avg_vol:.0f}%")
        print(f"  High-opportunity tickers  : "
              f"{C.green(', '.join(high_opp)) if high_opp else C.red('None')}")
        print(f"  Potentially overbought    : "
              f"{C.red(', '.join(overbought)) if overbought else C.green('None')}")
        print(f"  Top-ranked name           : "
              f"{C.bold(top.ticker)} (score {top.score})")
        print()

        if avg_score >= 65:
            verdict = C.green("✅  SECTOR STILL HAS LEGS — strong setups remain")
            boat    = "You have NOT missed the boat. Multiple valid entry setups exist."
            cash    = ("Lump-sum or DCA into top-ranked names, "
                       "or buy the SMH/SOXX ETF basket for diversified exposure.")
        elif avg_score >= 45:
            verdict = C.yellow("⚡  MIXED — sector has run hard; selective opportunity remains")
            boat    = "You may have missed the easiest gains; pullback buyers can still find good R/R."
            cash    = ("Use DCA or GTC limit orders rather than lump-sum. "
                       "Cherry-pick highest-scored individual names.")
        else:
            verdict = C.red("⚠️  CAUTION — broad sector extended or losing momentum")
            boat    = "Entering now carries elevated timing risk. Patience likely rewards with a better entry."
            cash    = ("Stay flat or wait for RSI to reset below 55. "
                       "Deploy a partial starter position only.")

        print(f"  Verdict          : {verdict}")
        print(f"  Missed the boat? : {boat}")
        print(f"  Cash playbook    : {cash}")
        print(f"\n{'═' * self.W}\n")

    # ── Private detail printer ────────────────────────────────────────────────

    def _print_one(self, r: AnalysisResult, show_options: bool) -> None:
        ind = r.ind
        td  = r.td
        W   = self.W

        print(f"\n{'═' * W}")
        print(C.bold(f"  {r.ticker}  —  {r.name}"))
        print(f"{'─' * W}")

        # Technicals
        print(f"  {'Price:':<28} ${ind.price:,.2f}   "
              f"ATR ${ind.atr:.2f} (±{ind.atr/ind.price*100:.1f}%/day)   "
              f"30d vol {ind.vol_30d_ann:.0f}%")
        print(f"  {'Opportunity Score:':<28} {C.score(ind.score)} / 100")
        print(f"  {'Trend:':<28} {ind.trend}")
        rsi_lbl = ("⚠ Overbought" if ind.rsi > 70
                   else "↙ Oversold" if ind.rsi < 30 else "✓ Neutral")
        print(f"  {'RSI (14):':<28} {ind.rsi:.1f}  {rsi_lbl}")
        stk_lbl = ("⚠ Overbought zone" if ind.stoch_k > 80
                   else "↙ Oversold zone" if ind.stoch_k < 20 else "Neutral")
        print(f"  {'Stochastic %K:':<28} {ind.stoch_k:.1f}  {stk_lbl}")
        print(f"  {'Bollinger Band %:':<28} {ind.bb_pct*100:.0f}%  "
              f"(band width {ind.bb_width*100:.1f}%)")
        print(f"  {'MACD Histogram:':<28} {ind.macd_hist:+.4f}  "
              f"{'↑ Positive' if ind.macd_hist > 0 else '↓ Negative'}")
        print(f"  {'ADX (trend strength):':<28} {ind.adx:.1f}  "
              f"{'Strong (>25)' if ind.adx > 25 else 'Weak / Ranging'}")
        print(f"  {'50-day SMA:':<28} ${ind.sma50:,.2f}  "
              f"({(ind.pct_from_50sma or 0):+.1f}% from price)")
        print(f"  {'200-day SMA:':<28} ${ind.sma200:,.2f}  "
              f"({(ind.pct_from_200sma or 0):+.1f}% from price)")
        print(f"  {'VWAP (approx):':<28} ${ind.vwap:,.2f}  "
              f"({(ind.pct_from_vwap or 0):+.1f}% from price)")
        print(f"  {'Support / Resistance:':<28} "
              f"${ind.support:,.2f}  /  ${ind.resistance:,.2f}")
        if ind.golden_cross:
            print(f"  {'Golden Cross:':<28} "
                  f"{C.green('YES — price > 50-SMA > 200-SMA ★')}")

        # Returns
        print(f"\n  {'─ Returns ─'}")
        print(f"  1W:{C.pct(ind.ret_1w)}  1M:{C.pct(ind.ret_1m)}  "
              f"3M:{C.pct(ind.ret_3m)}  6M:{C.pct(ind.ret_6m)}  "
              f"1Y:{C.pct(ind.ret_1y)}")
        if r.rs_vs_spy is not None:
            lbl = "outperforming" if r.rs_vs_spy > 0 else "underperforming"
            print(f"  vs SPY (3M): {C.pct(r.rs_vs_spy)}  ({lbl} market)")

        # Risk
        print(f"\n  {'─ Risk ─'}")
        print(f"  {'Max Drawdown (period):':<28} {C.pct(ind.max_dd)}")
        if ind.sharpe_est is not None:
            sh    = ind.sharpe_est
            grade = "Good" if sh > 1 else ("Fair" if sh > 0.5 else "Poor")
            print(f"  {'Sharpe Ratio (est.):':<28} {sh:.2f}  ({grade})")
        if td.beta:
            bv   = td.beta
            blbl = ("Higher" if bv > 1.2 else
                    "Similar" if bv > 0.8 else "Lower")
            print(f"  {'Beta:':<28} {bv:.2f}  ({blbl} volatility than market)")

        # Score breakdown
        print(f"\n  Score components:", end="")
        for k, v in ind.score_detail.items():
            print(f"  {k}={v}", end="")
        print()

        # Fundamentals
        print(f"\n  {'─ Fundamentals ─'}")
        print(f"  {'P/E (TTM):':<28} {C.ratio(td.pe_ttm)}")
        pe_lbl = ("✓ Reasonable" if td.pe_fwd and td.pe_fwd < 20
                  else "⚡ Premium"  if td.pe_fwd and td.pe_fwd < 35
                  else "⚠ Expensive" if td.pe_fwd else "")
        print(f"  {'Forward P/E:':<28} {C.ratio(td.pe_fwd)}  {pe_lbl}")
        peg_lbl = ("✓ <1 (growth at discount)" if td.peg and td.peg < 1
                   else "Fair (1-2)"            if td.peg and td.peg < 2
                   else "⚠ >2"                  if td.peg else "")
        print(f"  {'PEG Ratio:':<28} {C.ratio(td.peg)}  {peg_lbl}")
        print(f"  {'Revenue Growth (TTM):':<28} "
              f"{C.pct(td.rev_growth * 100 if td.rev_growth else None)}")
        if td.dividend_yield:
            print(f"  {'Dividend Yield:':<28} {td.dividend_yield*100:.2f}%")
        if td.market_cap:
            print(f"  {'Market Cap:':<28} ${td.market_cap/1e9:.1f}B")
        if td.analyst_target and ind.price:
            up = (td.analyst_target / ind.price - 1) * 100
            print(f"  {'Analyst Mean Target:':<28} ${td.analyst_target:,.2f}  "
                  f"({up:+.1f}% implied {'upside' if up > 0 else 'downside'})")
        if td.week52_high and td.week52_low:
            print(f"  {'52-week range:':<28} "
                  f"${td.week52_low:,.2f} – ${td.week52_high:,.2f}  "
                  f"({(ind.price/td.week52_high - 1)*100:+.1f}% from 52w high)")

        # Cash strategies
        print(f"\n  {C.bold('━' * (W - 2))}")
        print(f"  {C.bold('CASH STRATEGIES  (no options required)')}")
        print(f"  {C.bold('━' * (W - 2))}")
        for idx, strat in enumerate(r.cash_strats, 1):
            sname = strat.name
            print(f"\n  {C.bold(f'  Strategy {idx}: {sname}')}")
            print(f"    Action    : {strat.action}")
            print(f"    Rationale : {strat.rationale}")
            print(f"    Execution :")
            for tip in strat.tips:
                print(f"      • {tip}")

        # Options
        if show_options and r.opt_strat:
            print(f"\n  {C.bold('─ Options Add-On (optional) ─')}")
            snap = r.opt_strat.snap
            if snap.error:
                print(f"  ⚠  {snap.error}")
            else:
                print(f"  {'Nearest expiry:':<28} {snap.expiry or 'N/A'}")
                print(f"  {'ATM Call IV:':<28} {C.flt(snap.atm_call_iv, 1, '%')}")
                print(f"  {'ATM Put IV:':<28} {C.flt(snap.atm_put_iv,  1, '%')}")
                if snap.pc_ratio is not None:
                    sent = ("Bearish"            if snap.pc_ratio > 1.5 else
                            "Slightly Defensive" if snap.pc_ratio > 1.0 else
                            "Bullish/Speculative" if snap.pc_ratio < 0.5 else
                            "Neutral")
                    print(f"  {'Put/Call OI ratio:':<28} "
                          f"{snap.pc_ratio:.2f}  ({sent})")
            print(f"  Suggested: {r.opt_strat.action}")

        print(f"\n  {C.yellow('⚠  Educational only — NOT financial advice. '
                              'Consult a licensed advisor.')}")
