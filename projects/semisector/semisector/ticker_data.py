"""
semisector/ticker_data.py
─────────────────────────
TickerData — fetches and stores raw OHLCV price history and
Yahoo Finance fundamentals for one ticker symbol.

This class is a pure data container; it contains no analysis logic.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Optional

warnings.filterwarnings("ignore")

import yfinance as yf
import pandas as pd

from semisector.config import ETF_TICKERS, BASKET_TICKERS


@dataclass
class TickerData:
    """
    Container for raw OHLCV price history and Yahoo Finance fundamentals.

    Construct via the class method:
        td = TickerData.fetch("NVDA", "1y")

    Or build manually for testing:
        td = TickerData(ticker="NVDA", period="1y", ohlcv=my_df, ...)
    """

    ticker: str
    period: str
    ohlcv:  Optional[pd.DataFrame] = field(default=None, repr=False)

    # ── Fundamentals (populated by _load_fundamentals) ────────────────────────
    short_name:       str            = ""
    pe_ttm:           Optional[float] = None
    pe_fwd:           Optional[float] = None
    peg:              Optional[float] = None
    rev_growth:       Optional[float] = None
    earnings_growth:  Optional[float] = None
    debt_eq:          Optional[float] = None
    market_cap:       Optional[float] = None
    beta:             Optional[float] = None
    sector:           str            = "N/A"
    dividend_yield:   Optional[float] = None
    week52_high:      Optional[float] = None
    week52_low:       Optional[float] = None
    analyst_target:   Optional[float] = None

    # ── Constructors ──────────────────────────────────────────────────────────

    @classmethod
    def fetch(cls, ticker: str, period: str) -> "TickerData":
        """
        Download OHLCV from Yahoo Finance and load fundamentals.
        Returns a TickerData with ohlcv=None if download fails.
        """
        td = cls(ticker=ticker, period=period)
        try:
            df = yf.download(ticker, period=period,
                             auto_adjust=True, progress=False)
            if not df.empty and len(df) >= 50:
                df.columns = [
                    c[0].lower() if isinstance(c, tuple) else c.lower()
                    for c in df.columns
                ]
                td.ohlcv = df
        except Exception as e:
            print(f"  ⚠  {ticker} price download: {e}")

        td._load_fundamentals()
        return td

    # ── Private helpers ───────────────────────────────────────────────────────

    def _load_fundamentals(self) -> None:
        """Pull fundamentals from yfinance .info."""
        try:
            info = yf.Ticker(self.ticker).info
            self.short_name     = (info.get("shortName") or self.ticker)[:24]
            self.pe_ttm         = info.get("trailingPE")
            self.pe_fwd         = info.get("forwardPE")
            self.peg            = info.get("pegRatio")
            self.rev_growth     = info.get("revenueGrowth")
            self.earnings_growth= info.get("earningsQuarterlyGrowth")
            self.debt_eq        = info.get("debtToEquity")
            self.market_cap     = info.get("marketCap")
            self.beta           = info.get("beta")
            self.sector         = info.get("sector") or "N/A"
            self.dividend_yield = info.get("dividendYield")
            self.week52_high    = info.get("fiftyTwoWeekHigh")
            self.week52_low     = info.get("fiftyTwoWeekLow")
            self.analyst_target = info.get("targetMeanPrice")
        except Exception:
            pass

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_valid(self) -> bool:
        """True if OHLCV data was successfully downloaded."""
        return self.ohlcv is not None

    @property
    def is_etf(self) -> bool:
        return self.ticker in ETF_TICKERS

    @property
    def in_basket(self) -> bool:
        return self.ticker in BASKET_TICKERS
