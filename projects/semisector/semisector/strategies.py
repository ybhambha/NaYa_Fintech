"""
semisector/strategies.py
────────────────────────
Strategy class hierarchy:

    Strategy (ABC)                 — shared interface & helpers
      ├─ FullBuyStrategy           — lump-sum buy
      ├─ DCAStrategy               — dollar-cost averaging
      ├─ PullbackBuyStrategy       — GTC limit order on pullback
      ├─ MomentumSwingStrategy     — short-term directional trade
      ├─ MeanReversionStrategy     — oversold bounce
      ├─ ETFRotationStrategy       — swap single-name for ETF
      ├─ BasketStrategy            — diversified sector basket
      ├─ PairTradeStrategy         — long strong / hedge weak
      ├─ PartialTrimStrategy       — take profit on existing position
      ├─ StayFlatStrategy          — explicit wait / do-nothing
      └─ OptionsStrategy           — options overlay (all approaches)

Each subclass implements:
    name          — short display label
    action        — one concrete sentence: what to do
    rationale     — why this fits the current setup
    tips          — list of 3–5 execution tips
    is_applicable — True when the strategy fits current indicators
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass

import yfinance as yf

from semisector.config import ETF_TICKERS
from semisector.indicators import IndicatorEngine


# ══════════════════════════════════════════════════════════════════════════════
#  Abstract base
# ══════════════════════════════════════════════════════════════════════════════

class Strategy(ABC):
    """
    Abstract base for all strategy types.
    Shared helper properties (stop_loss, shares, pullback_target, etc.)
    are defined here so subclasses stay focused on their own logic.
    """

    def __init__(self, ticker: str, ind: IndicatorEngine,
                 budget: float) -> None:
        self.ticker = ticker
        self.ind    = ind
        self.budget = budget

    # ── Abstract interface ────────────────────────────────────────────────────

    @property
    @abstractmethod
    def name(self) -> str:
        """Short display name."""

    @property
    @abstractmethod
    def action(self) -> str:
        """One-sentence concrete action."""

    @property
    @abstractmethod
    def rationale(self) -> str:
        """Why this strategy fits the current setup."""

    @property
    @abstractmethod
    def tips(self) -> list[str]:
        """3–5 execution tips."""

    @abstractmethod
    def is_applicable(self) -> bool:
        """Return True when this strategy is relevant."""

    # ── Shared helpers ────────────────────────────────────────────────────────

    @property
    def stop_loss(self) -> float:
        return round(self.ind.price - 1.5 * self.ind.atr, 2)

    @property
    def shares(self) -> int:
        risk = max(self.ind.price - self.stop_loss, 0.01)
        return max(1, int((self.budget * 0.01) / risk))

    @property
    def pullback_target(self) -> float:
        return round(max(self.ind.sma50, self.ind.price * 0.93), 2)

    @property
    def upside_pct(self) -> float:
        return (self.ind.resistance / self.ind.price - 1) * 100

    @property
    def downside_pct(self) -> float:
        if self.ind.support < self.ind.price:
            return max((self.ind.price / self.ind.support - 1) * 100, 0.01)
        return 5.0

    @property
    def rr_ratio(self) -> str:
        return f"{self.upside_pct / self.downside_pct:.1f}"

    @property
    def ret_3m(self) -> float:
        return self.ind.ret_3m or 0.0


# ══════════════════════════════════════════════════════════════════════════════
#  Cash strategy subclasses
# ══════════════════════════════════════════════════════════════════════════════

class FullBuyStrategy(Strategy):
    """Lump-sum buy — high score, not overbought, strong trend."""

    @property
    def name(self) -> str:
        return "🟢 Full Buy — Lump-Sum"

    def is_applicable(self) -> bool:
        return (self.ind.score >= 70
                and self.ind.rsi < 65
                and self.ind.adx > 22)

    @property
    def action(self) -> str:
        n = max(1, int(self.budget / self.ind.price))
        return (f"Buy {n} shares of {self.ticker} at market "
                f"(≈${self.ind.price:,.2f}). "
                f"Stop-loss at ${self.stop_loss:,.2f}.")

    @property
    def rationale(self) -> str:
        gc = " Golden cross in place." if self.ind.golden_cross else ""
        return (f"Score {self.ind.score}/100, RSI {self.ind.rsi:.0f} (not overbought), "
                f"ADX {self.ind.adx:.0f} (strong trend). "
                f"Risk/reward ≈ {self.rr_ratio}×.{gc}")

    @property
    def tips(self) -> list[str]:
        return [
            f"Use a limit order at or just below ${self.ind.price * 1.002:,.2f} "
            "to avoid gap-up fills.",
            f"Hard stop-loss at ${self.stop_loss:,.2f} "
            f"(1.5× ATR = {(1 - self.stop_loss/self.ind.price)*100:.1f}% below entry).",
            f"First profit-take at ${self.ind.resistance:,.2f} "
            f"(+{self.upside_pct:.1f}% — 60-day resistance).",
            "Cap at 5–8% of total portfolio in any single name.",
        ]


class DCAStrategy(Strategy):
    """Dollar-cost averaging — spreads entry risk over time."""

    def _params(self) -> tuple[str, float, int]:
        if self.ind.rsi > 62 or self.ret_3m > 25:
            return "weekly", round(self.budget / 8, 0), 8
        return "bi-weekly", round(self.budget / 5, 0), 10

    @property
    def name(self) -> str:
        freq, _, periods = self._params()
        return f"📅 Dollar-Cost Averaging ({freq.title()}, {periods} periods)"

    def is_applicable(self) -> bool:
        return self.ind.score >= 50

    @property
    def action(self) -> str:
        freq, amt, periods = self._params()
        return (f"Invest ${amt:,.0f} in {self.ticker} every {freq} "
                f"for {periods} periods. Total: ${self.budget:,.0f}.")

    @property
    def rationale(self) -> str:
        return (f"Sector up {self.ret_3m:+.0f}% in 3 months — timing risk is real. "
                "DCA removes the 'did I buy the top?' problem by spreading "
                "purchases across time and averaging your cost basis.")

    @property
    def tips(self) -> list[str]:
        is_etf = self.ticker in ETF_TICKERS
        return [
            "Set a recurring calendar reminder — discipline beats market-timing.",
            "Track your average cost basis after each tranche.",
            f"Pause if price falls below ${self.ind.sma200:,.2f} (200-SMA) and re-assess.",
            ("This IS the ETF — ideal DCA vehicle." if is_etf
             else "ETF alternative: SMH or SOXX for diversified DCA."),
        ]


class PullbackBuyStrategy(Strategy):
    """GTC limit order — wait for the stock to come to you."""

    @property
    def name(self) -> str:
        return "⏳ Pullback Buy — GTC Limit Order"

    def is_applicable(self) -> bool:
        return self.ind.rsi > 58 or self.ret_3m > 18

    @property
    def action(self) -> str:
        tgt = self.pullback_target
        return (f"Set a Good-Till-Cancelled limit buy for {self.ticker} at "
                f"${tgt:,.2f} "
                f"({(self.ind.price / tgt - 1)*100:.1f}% below today). "
                f"Target: ${self.ind.resistance:,.2f}. Stop: ${self.stop_loss:,.2f}.")

    @property
    def rationale(self) -> str:
        return (f"RSI {self.ind.rsi:.0f} and {self.ret_3m:+.0f}% 3-month gain suggest "
                f"extended conditions. Waiting for a pullback to "
                f"${self.pullback_target:,.2f} (50-SMA / −7%) improves entry R/R.")

    @property
    def tips(self) -> list[str]:
        return [
            f"Primary limit zone: ${self.ind.sma50:,.2f} (50-day SMA — natural support).",
            f"Deeper limit: ${self.ind.bb_lower:,.2f} (lower Bollinger Band).",
            "Cancel if earnings or guidance materially change the thesis.",
            "Combine with a −5% price alert for manual monitoring.",
            "This strategy requires patience — it may take weeks to fill.",
        ]


class MomentumSwingStrategy(Strategy):
    """Short-term directional swing trade on confirmed strong trend."""

    @property
    def _swing_target(self) -> float:
        return round(self.ind.price + 2.5 * self.ind.atr, 2)

    @property
    def name(self) -> str:
        return "⚡ Momentum Swing Trade (1–3 weeks)"

    def is_applicable(self) -> bool:
        return (self.ind.score >= 60
                and self.ind.adx > 25
                and self.ind.macd_hist > 0
                and self.ind.rsi < 70)

    @property
    def action(self) -> str:
        return (f"Buy {self.shares} shares of {self.ticker} at market "
                f"(${self.ind.price:,.2f}). "
                f"Target: ${self._swing_target:,.2f} "
                f"(+{(self._swing_target/self.ind.price - 1)*100:.1f}%). "
                f"Stop: ${self.stop_loss:,.2f}. Hold: 5–15 trading days.")

    @property
    def rationale(self) -> str:
        return (f"ADX {self.ind.adx:.0f} confirms strong trend. "
                f"MACD histogram positive (momentum building). "
                f"ATR-based target = 2.5× risk → 2.5:1 reward/risk ratio.")

    @property
    def tips(self) -> list[str]:
        return [
            "Raise stop to breakeven once position is up 1.5× ATR.",
            "Exit if RSI exceeds 78 regardless of price (momentum exhaustion).",
            "Look for above-average volume on entry day for confirmation.",
            "This is a TRADE — define your exit rules BEFORE entering.",
            "Do not convert a losing trade into a long-term investment.",
        ]


class MeanReversionStrategy(Strategy):
    """Oversold bounce when RSI is depressed but long-term trend intact."""

    @property
    def name(self) -> str:
        return "🔄 Mean-Reversion Buy — Oversold Bounce"

    def is_applicable(self) -> bool:
        return self.ind.rsi < 38 and self.ind.price > self.ind.sma200 * 0.90

    @property
    def action(self) -> str:
        return (f"Buy {self.shares} shares of {self.ticker} near "
                f"${self.ind.price:,.2f}. "
                f"Target: ${self.ind.sma50:,.2f} (50-SMA, "
                f"+{(self.ind.sma50/self.ind.price - 1)*100:.1f}%). "
                f"Stop: ${self.stop_loss:,.2f}.")

    @property
    def rationale(self) -> str:
        return (f"RSI {self.ind.rsi:.0f} is oversold (< 38) while price remains above "
                "200-SMA — long-term trend intact. "
                "Bounces to the 50-SMA are statistically common from this setup.")

    @property
    def tips(self) -> list[str]:
        return [
            "Wait for one green candle to confirm the bounce — don't bottom-fish blindly.",
            "Use a tight stop: close below today's low invalidates the thesis.",
            f"Trim at the 50-SMA (${self.ind.sma50:,.2f}); hold beyond only if volume is strong.",
            "Confirm SPY is not simultaneously in a downtrend.",
        ]


class ETFRotationStrategy(Strategy):
    """Swap single-name risk for a sector ETF."""

    def _etf(self) -> str:
        return "SMH" if self.ret_3m > 20 else "SOXX"

    @property
    def name(self) -> str:
        return f"🔀 ETF Rotation — Swap {self.ticker} Risk for {self._etf()}"

    def is_applicable(self) -> bool:
        return self.ticker not in ETF_TICKERS

    @property
    def action(self) -> str:
        return (f"Instead of (or alongside) single-stock {self.ticker}, "
                f"buy ${self.budget:,.0f} of {self._etf()} via lump-sum or DCA.")

    @property
    def rationale(self) -> str:
        return (f"Reduces single-name concentration risk while maintaining full "
                f"sector exposure. {self._etf()} holds 25-30 semiconductor names — "
                "one earnings miss won't crater the position.")

    @property
    def tips(self) -> list[str]:
        return [
            "SMH: more NVDA-heavy (higher AI beta). SOXX: more balanced (10% cap).",
            "SOXL is 3× leveraged — only for very short-term tactical traders.",
            "ETFs work well as DCA vehicles with automatic investment plans.",
            "Both SMH and SOXX expense ratios ≈ 0.35% — very low cost.",
        ]


class BasketStrategy(Strategy):
    """Diversified basket across all semiconductor sub-sectors."""

    _BASKET = ["NVDA", "MU", "AMAT", "TXN", "SMH"]

    @property
    def name(self) -> str:
        return "🧺 Diversified Semiconductor Basket"

    def is_applicable(self) -> bool:
        return self.ticker in self._BASKET

    @property
    def action(self) -> str:
        per = round(self.budget / len(self._BASKET), 0)
        return (f"Allocate ${per:,.0f} each to: {', '.join(self._BASKET)}. "
                f"Total: ${self.budget:,.0f}.")

    @property
    def rationale(self) -> str:
        return ("Covers all sub-sectors: AI compute (NVDA), memory (MU), "
                "equipment (AMAT), analog/power (TXN), ETF anchor (SMH). "
                "No single name > 20% of the position.")

    @property
    def tips(self) -> list[str]:
        return [
            "Rebalance quarterly back to equal weight.",
            "Replace any name that closes below its 200-SMA for 5+ consecutive days.",
            "Add LRCX or AVGO for broader equipment / networking exposure.",
            "Best suited for a 2–5 year hold tracking the AI infrastructure cycle.",
        ]


class PairTradeStrategy(Strategy):
    """Long best-scored name, hedge with weakest in sector."""

    @property
    def name(self) -> str:
        return "⚖️  Sector Pair / Relative Value"

    def is_applicable(self) -> bool:
        return self.ind.score >= 70 and self.ticker not in ETF_TICKERS

    @property
    def action(self) -> str:
        return (f"Long {self.ticker} (score {self.ind.score}). "
                "Underweight or short the lowest-scored name in the ranked table.")

    @property
    def rationale(self) -> str:
        return ("Isolates relative alpha between the strongest and weakest setup. "
                "If the whole sector corrects, the short leg partially offsets losses.")

    @property
    def tips(self) -> list[str]:
        return [
            "Dollar-neutral sizing: equal $ long and short reduces market-beta.",
            "Monitor daily — semiconductor correlations shift quickly.",
            "Close when the score gap narrows below 15 points.",
            "Note: the short leg requires a margin account.",
        ]


class PartialTrimStrategy(Strategy):
    """Take partial profits when position is extended."""

    @property
    def name(self) -> str:
        return "✂️  Partial Trim — Take Profit (Existing Holders)"

    def is_applicable(self) -> bool:
        return self.ind.rsi > 68 or self.ret_3m > 35

    @property
    def action(self) -> str:
        trail = round(1.5 * self.ind.atr, 2)
        return (f"Sell 25–33% of existing {self.ticker} position at market. "
                f"Apply a trailing stop of ${trail:,.2f} "
                f"({trail/self.ind.price*100:.1f}% below current price) to remainder.")

    @property
    def rationale(self) -> str:
        return (f"RSI {self.ind.rsi:.0f} and {self.ret_3m:+.0f}% 3-month gain signal "
                "extended conditions. Locking in partial profits removes emotional risk "
                "while keeping upside on the remainder.")

    @property
    def tips(self) -> list[str]:
        return [
            "Trim on UP days into strength — not during panicked selling.",
            "Reinvest proceeds into lower-RSI names from the ranked table.",
            "Consider short- vs. long-term capital gains tax timing.",
            f"Re-accumulate if price pulls back cleanly to ${self.ind.sma50:,.2f} (50-SMA).",
        ]


class StayFlatStrategy(Strategy):
    """Explicit 'do nothing' recommendation when setup is poor."""

    @property
    def name(self) -> str:
        return "🚫 Stay Flat — Wait for a Better Entry"

    def is_applicable(self) -> bool:
        return self.ind.score < 40 and self.ind.rsi > 68

    @property
    def action(self) -> str:
        return (f"Do NOT open a new position in {self.ticker} at "
                f"${self.ind.price:,.2f}. "
                f"Set a price alert at ${self.pullback_target:,.2f} and revisit.")

    @property
    def rationale(self) -> str:
        return (f"Score {self.ind.score}/100 + RSI {self.ind.rsi:.0f} = poor entry "
                "risk/reward. The stock needs to digest recent gains.")

    @property
    def tips(self) -> list[str]:
        return [
            f"Set an alert at ${self.pullback_target:,.2f} (50-SMA / ≈ −7%).",
            f"Set a deeper alert at ${self.ind.sma200:,.2f} (200-SMA).",
            "Deploy capital into the highest-scored name from the ranked table instead.",
            "Use the waiting period to study upcoming earnings / analyst revisions.",
        ]


# ══════════════════════════════════════════════════════════════════════════════
#  Options snapshot + strategy
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class OptionsSnapshot:
    """Raw data pulled from the nearest-expiry options chain."""

    expiry:      Optional[str]   = None
    atm_call_iv: Optional[float] = None
    atm_put_iv:  Optional[float] = None
    pc_ratio:    Optional[float] = None
    error:       Optional[str]   = None

    @classmethod
    def fetch(cls, ticker: str, price: float) -> "OptionsSnapshot":
        snap = cls()
        try:
            tk  = yf.Ticker(ticker)
            exp = tk.options
            if not exp:
                snap.error = "No options listed"
                return snap
            target = datetime.today() + timedelta(days=14)
            chosen = next(
                (e for e in exp
                 if datetime.strptime(e, "%Y-%m-%d") >= target),
                exp[0]
            )
            chain = tk.option_chain(chosen)
            calls, puts = chain.calls.copy(), chain.puts.copy()
            if not calls.empty:
                calls["dist"]    = (calls["strike"] - price).abs()
                snap.atm_call_iv = float(
                    calls.loc[calls["dist"].idxmin()].get(
                        "impliedVolatility", 0)) * 100
            if not puts.empty:
                puts["dist"]    = (puts["strike"] - price).abs()
                snap.atm_put_iv = float(
                    puts.loc[puts["dist"].idxmin()].get(
                        "impliedVolatility", 0)) * 100
            c_oi = calls["openInterest"].sum() if not calls.empty else 0
            p_oi = puts["openInterest"].sum()  if not puts.empty else 0
            if c_oi > 0:
                snap.pc_ratio = round(p_oi / c_oi, 2)
            snap.expiry = chosen
        except Exception as e:
            snap.error = str(e)
        return snap


class OptionsStrategy(Strategy):
    """
    Options overlay strategy.
    The suggested approach is derived at runtime from score / RSI / IV.
    """

    def __init__(self, ticker: str, ind: IndicatorEngine,
                 budget: float, snap: OptionsSnapshot) -> None:
        super().__init__(ticker, ind, budget)
        self.snap = snap

    @property
    def name(self) -> str:
        return "🎯 Options Strategy"

    def is_applicable(self) -> bool:
        return self.snap.error is None

    @property
    def _suggestion(self) -> str:
        iv    = self.snap.atm_call_iv or 30
        score = self.ind.score
        rsi   = self.ind.rsi
        pc    = self.snap.pc_ratio
        if score >= 70:
            return ("📈 Bull Call Spread (high IV — spread lowers premium cost)"
                    if iv >= 40 else
                    "📈 Long Call (moderate IV — direct upside; size 1-2% of portfolio)")
        elif score >= 50:
            if rsi > 65:
                return "⏳ Cash-Secured Put (sell OTM put 5–10% below — premium income or own at discount)"
            elif iv > 50:
                return "⏳ Iron Condor / Short Strangle (elevated IV — sell premium, profit from consolidation)"
            else:
                return "⏳ Covered Call (own shares, sell ATM call to reduce cost basis)"
        else:
            if rsi > 70:
                return "⚠️  Protective Put / Collar (hedge existing position against overextension)"
            elif pc and pc > 1.2:
                return "⚠️  Wait or Long Put (elevated P/C ratio — defensive posture)"
            return "⚠️  Wait for Better Setup (RSI reset below 50 before bullish options play)"

    @property
    def action(self) -> str:
        return self._suggestion

    @property
    def rationale(self) -> str:
        from semisector.color_helper import C
        iv  = C.flt(self.snap.atm_call_iv, 1, "%")
        pc  = C.flt(self.snap.pc_ratio, 2)
        exp = self.snap.expiry or "N/A"
        return f"Nearest expiry: {exp}. ATM Call IV: {iv}. Put/Call OI ratio: {pc}."

    @property
    def tips(self) -> list[str]:
        return [
            "Options carry substantial risk — size to ≤ 2% of portfolio per trade.",
            "Always define max loss before entry (spreads cap your downside).",
            "IV crush after earnings can wipe out long option premium.",
            "Consult a licensed advisor before trading options.",
        ]
