"""
semisector/config.py
────────────────────
All application-wide constants and default configuration values.
Import this module anywhere you need a shared constant — never hard-code
these values in other modules.
"""

# ── Default ticker universe ───────────────────────────────────────────────────
DEFAULT_TICKERS: list[str] = [
    # Chip design / AI compute
    "NVDA", "AMD", "AVGO", "QCOM", "MRVL",
    # Memory
    "MU",
    # Equipment & power
    "AMAT", "LRCX", "ON", "TXN",
    # Sector ETFs
    "SMH", "SOXX",
]

# ── Sets used for ticker classification ──────────────────────────────────────
ETF_TICKERS: set[str] = {"SMH", "SOXX", "SOXL", "XLK", "QQQ", "FTXL"}
BASKET_TICKERS: set[str] = {"NVDA", "MU", "AMAT", "TXN", "SMH"}

# ── Analysis defaults ─────────────────────────────────────────────────────────
DEFAULT_PERIOD:  str   = "1y"       # yfinance period string
DEFAULT_BUDGET:  float = 10_000.0   # USD per ticker
BENCH_TICKER:    str   = "SPY"      # benchmark for relative-strength calc
RISK_FREE_RATE:  float = 0.0525     # annualised, used in Sharpe estimate

# ── Database ──────────────────────────────────────────────────────────────────
DEFAULT_DB_PATH: str = "semiconductor_analysis.db"

# ── Technical indicator parameters ───────────────────────────────────────────
RSI_WINDOW:       int = 14
RSI_SLOW_WINDOW:  int = 21
MACD_FAST:        int = 12
MACD_SLOW:        int = 26
MACD_SIGNAL:      int = 9
BB_WINDOW:        int = 20
BB_STD:           int = 2
ADX_WINDOW:       int = 14
ATR_WINDOW:       int = 14
STOCH_WINDOW:     int = 14
SMA_SHORT:        int = 20
SMA_MID:          int = 50
SMA_LONG:         int = 200
EMA_WINDOW:       int = 21
SUPPORT_LOOKBACK: int = 60    # days used for support/resistance percentiles

# ── Scoring thresholds ────────────────────────────────────────────────────────
SCORE_HIGH:      int = 70    # score >= this → green / high opportunity
SCORE_MED:       int = 45    # score >= this → yellow / moderate
RSI_OVERBOUGHT:  int = 70
RSI_OVERSOLD:    int = 30
ADX_STRONG:      int = 25
