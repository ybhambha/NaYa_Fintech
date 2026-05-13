# semisector — Semiconductor Sector Opportunity Analyzer

[![CI](https://github.com/ybhambha/semisector/actions/workflows/ci.yml/badge.svg)](https://github.com/ybhambha/semisector/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A fully object-oriented Python tool that fetches live market data, scores
semiconductor / power / memory stocks and ETFs on a **0–100 opportunity scale**,
and recommends concrete **cash** and **options** strategies — all persisted to
a local **SQLite** database for trend tracking over time.

---

## Covered Universe

| Category | Tickers |
|---|---|
| Chip design / AI | NVDA · AMD · AVGO · QCOM · MRVL |
| Memory | MU |
| Equipment & power | AMAT · LRCX · ON · TXN |
| Sector ETFs | SMH · SOXX |

---

## Features

- **Opportunity Score 0–100** — composite of RSI, Bollinger Bands, 50-SMA, MACD, ADX, Stochastic, Golden Cross
- **10 cash strategies** — Full Buy, DCA, Pullback Limit, Momentum Swing, Mean Reversion, ETF Rotation, Basket, Pair Trade, Partial Trim, Stay Flat
- **Options overlay** — Bull Call Spread, Long Call, Cash-Secured Put, Iron Condor, Covered Call, Protective Put
- **Fundamentals** — Forward P/E, PEG, Revenue Growth, Beta, Analyst targets
- **Risk metrics** — Max Drawdown, Sharpe Ratio, 30-day annualised volatility
- **SQLite persistence** — every run saved with full OHLCV history, indicators, and strategies
- **Relative strength** vs SPY (3-month)
- **GitHub Actions CI** — runs pytest on Python 3.10 / 3.11 / 3.12

---

## Project Structure

```
semisector/
├── semisector/               ← Python package
│   ├── __init__.py
│   ├── config.py             ← All constants & defaults
│   ├── color_helper.py       ← Terminal colour formatting
│   ├── ticker_data.py        ← TickerData (OHLCV + fundamentals)
│   ├── indicators.py         ← IndicatorEngine (all technicals + score)
│   ├── strategies.py         ← Strategy ABC + 10 cash + options subclasses
│   ├── strategy_engine.py    ← StrategyEngine (evaluation & ranking)
│   ├── models.py             ← AnalysisResult dataclass
│   ├── reporter.py           ← Reporter (all console output)
│   ├── database.py           ← DatabaseManager (SQLite)
│   └── analyzer.py           ← Analyzer (top-level orchestrator)
├── tests/
│   ├── conftest.py           ← Shared pytest fixtures (no network)
│   ├── test_indicators.py
│   ├── test_strategies.py
│   └── test_database.py
├── data/                     ← SQLite .db files land here (git-ignored)
├── docs/                     ← Extended documentation
├── .github/workflows/ci.yml  ← GitHub Actions CI
├── main.py                   ← CLI entry point
├── setup.py
├── requirements.txt
├── requirements-dev.txt
└── .gitignore
```

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/ybhambha/semisector.git
cd semisector

# 2. Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run
python main.py
```

---

## Usage

```bash
# Full analysis — all default tickers, 1-year history, $10k budget
python main.py

# Custom tickers
python main.py --tickers NVDA AMD MU AMAT

# Shorter history window with larger budget
python main.py --period 6mo --budget 25000

# Quick ranked table only (no per-ticker detail)
python main.py --summary-only

# Cash strategies only — skip options chain fetch (faster)
python main.py --no-options

# Save database to a custom path
python main.py --db data/my_runs.db

# Disable database entirely
python main.py --no-db
```

---

## SQLite Schema

The database (`semiconductor_analysis.db` by default) contains five tables:

| Table | Contents |
|---|---|
| `runs` | One row per execution — timestamp, period, budget, tickers |
| `ticker_snapshot` | Every indicator & fundamental per ticker/run |
| `price_history` | Full OHLCV rows per ticker/run |
| `strategies` | Every strategy generated (action, rationale, tips) |
| `options_snapshot` | ATM call/put IV, put/call ratio, expiry |

### Example queries

```sql
-- Which tickers scored ≥ 70 in the latest run?
SELECT ticker, score, rsi, trend
FROM ticker_snapshot
WHERE run_id = (SELECT MAX(id) FROM runs) AND score >= 70;

-- How has NVDA's score trended across all runs?
SELECT r.run_at, t.score, t.rsi, t.ret_3m
FROM ticker_snapshot t JOIN runs r ON t.run_id = r.id
WHERE t.ticker = 'NVDA'
ORDER BY r.run_at;

-- What strategies were suggested for MU in the last run?
SELECT kind, name, action
FROM strategies
WHERE run_id = (SELECT MAX(id) FROM runs)
  AND ticker = 'MU';
```

---

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
pytest tests/ -v --cov=semisector --cov-report=term-missing
```

---

## Class Hierarchy

```
ColorHelper          — terminal colour formatting
TickerData           — OHLCV + fundamentals container (dataclass)
IndicatorEngine      — computes all technicals + Opportunity Score
Strategy (ABC)
  ├─ FullBuyStrategy
  ├─ DCAStrategy
  ├─ PullbackBuyStrategy
  ├─ MomentumSwingStrategy
  ├─ MeanReversionStrategy
  ├─ ETFRotationStrategy
  ├─ BasketStrategy
  ├─ PairTradeStrategy
  ├─ PartialTrimStrategy
  ├─ StayFlatStrategy
  └─ OptionsStrategy
StrategyEngine       — evaluates & returns applicable strategies
AnalysisResult       — aggregated ticker snapshot (dataclass)
Reporter             — all console output
DatabaseManager      — SQLite persistence (context manager)
Analyzer             — top-level orchestrator
```

---

## Disclaimer

> **This tool is for educational and research purposes only.**
> It is NOT financial advice. All strategy suggestions are illustrative.
> Past performance does not guarantee future results.
> Consult a licensed financial advisor before making investment decisions.

---

## License

MIT © ybhambha
