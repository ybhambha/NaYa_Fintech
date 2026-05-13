"""
semisector/database.py
───────────────────────
DatabaseManager — all SQLite read/write operations.

Schema
──────
  runs             id · run_at · period · budget · tickers_json · notes
  ticker_snapshot  id · run_id · ticker · <every indicator & fundamental>
  price_history    id · run_id · ticker · date · open · high · low · close · volume
  strategies       id · run_id · ticker · kind · name · action · rationale · tips_json
  options_snapshot id · run_id · ticker · expiry · call_iv · put_iv · pc_ratio · error

Usage
─────
    # As a context manager (recommended)
    with DatabaseManager("semiconductor_analysis.db") as db:
        run_id = db.save_run(period, budget, tickers)
        for result in results:
            db.save_result(run_id, result)

    # Or manually
    db = DatabaseManager("semiconductor_analysis.db")
    run_id = db.save_run(...)
    db.save_result(run_id, result)
    db.close()
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Optional

from semisector.color_helper import C
from semisector.models       import AnalysisResult


class DatabaseManager:
    """
    Manages a SQLite database that persists every analysis run.
    Each save_result() call is wrapped in a single transaction,
    so a failure on one ticker never corrupts others.
    """

    # ── DDL ───────────────────────────────────────────────────────────────────
    _DDL = [
        """
        CREATE TABLE IF NOT EXISTS runs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at        TEXT    NOT NULL,
            period        TEXT    NOT NULL,
            budget        REAL    NOT NULL,
            tickers_json  TEXT    NOT NULL,
            notes         TEXT
        )""",
        """
        CREATE TABLE IF NOT EXISTS ticker_snapshot (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id          INTEGER NOT NULL REFERENCES runs(id),
            ticker          TEXT    NOT NULL,
            short_name      TEXT,
            -- price & technicals
            price           REAL,
            rsi             REAL,
            macd_hist       REAL,
            bb_pct          REAL,
            bb_width        REAL,
            bb_upper        REAL,
            bb_lower        REAL,
            sma20           REAL,
            sma50           REAL,
            sma200          REAL,
            ema21           REAL,
            vwap            REAL,
            adx             REAL,
            atr             REAL,
            stoch_k         REAL,
            golden_cross    INTEGER,
            trend           TEXT,
            score           INTEGER,
            score_detail    TEXT,
            -- returns
            ret_1w          REAL,
            ret_1m          REAL,
            ret_3m          REAL,
            ret_6m          REAL,
            ret_1y          REAL,
            rs_vs_spy       REAL,
            -- risk
            vol_30d_ann     REAL,
            max_dd          REAL,
            sharpe_est      REAL,
            -- levels
            support         REAL,
            resistance      REAL,
            pct_from_50sma  REAL,
            pct_from_200sma REAL,
            pct_from_vwap   REAL,
            -- fundamentals
            pe_ttm          REAL,
            pe_fwd          REAL,
            peg             REAL,
            rev_growth      REAL,
            earnings_growth REAL,
            debt_eq         REAL,
            market_cap      REAL,
            beta            REAL,
            sector          TEXT,
            dividend_yield  REAL,
            week52_high     REAL,
            week52_low      REAL,
            analyst_target  REAL
        )""",
        """
        CREATE TABLE IF NOT EXISTS price_history (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id   INTEGER NOT NULL REFERENCES runs(id),
            ticker   TEXT    NOT NULL,
            date     TEXT    NOT NULL,
            open     REAL,
            high     REAL,
            low      REAL,
            close    REAL    NOT NULL,
            volume   REAL
        )""",
        """
        CREATE TABLE IF NOT EXISTS strategies (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id     INTEGER NOT NULL REFERENCES runs(id),
            ticker     TEXT    NOT NULL,
            kind       TEXT    NOT NULL,
            name       TEXT    NOT NULL,
            action     TEXT,
            rationale  TEXT,
            tips_json  TEXT
        )""",
        """
        CREATE TABLE IF NOT EXISTS options_snapshot (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      INTEGER NOT NULL REFERENCES runs(id),
            ticker      TEXT    NOT NULL,
            expiry      TEXT,
            call_iv     REAL,
            put_iv      REAL,
            pc_ratio    REAL,
            error       TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS idx_snap_run    ON ticker_snapshot(run_id)",
        "CREATE INDEX IF NOT EXISTS idx_snap_ticker ON ticker_snapshot(ticker)",
        "CREATE INDEX IF NOT EXISTS idx_hist_run    ON price_history(run_id)",
        "CREATE INDEX IF NOT EXISTS idx_hist_ticker ON price_history(ticker)",
        "CREATE INDEX IF NOT EXISTS idx_strat_run   ON strategies(run_id)",
        "CREATE INDEX IF NOT EXISTS idx_opt_run     ON options_snapshot(run_id)",
    ]

    # ── Construction ──────────────────────────────────────────────────────────

    def __init__(self, db_path: str) -> None:
        from pathlib import Path
        self.db_path = db_path
        self._conn   = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode  = WAL")
        self._apply_schema()
        print(C.dim(f"  💾 Database: {Path(db_path).resolve()}"))

    def __enter__(self) -> "DatabaseManager":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ── Transaction helper ────────────────────────────────────────────────────

    @contextmanager
    def _transaction(self):
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            cur.close()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _apply_schema(self) -> None:
        with self._transaction() as cur:
            for stmt in self._DDL:
                cur.execute(stmt)

    # ── Write API ─────────────────────────────────────────────────────────────

    def save_run(self, period: str, budget: float,
                 tickers: list[str], notes: str = "") -> int:
        """Insert a new run record. Returns the run_id."""
        from datetime import datetime
        with self._transaction() as cur:
            cur.execute(
                "INSERT INTO runs (run_at, period, budget, tickers_json, notes) "
                "VALUES (?, ?, ?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"),
                 period, budget, json.dumps(tickers), notes)
            )
            return cur.lastrowid

    def save_result(self, run_id: int, result: AnalysisResult) -> None:
        """Persist one AnalysisResult atomically (snapshot + OHLCV + strategies + options)."""
        with self._transaction() as cur:
            self._insert_snapshot(cur, run_id, result)
            self._insert_price_history(cur, run_id, result)
            self._insert_strategies(cur, run_id, result)
            self._insert_options(cur, run_id, result)

    # ── Read API ──────────────────────────────────────────────────────────────

    def list_runs(self) -> list[dict]:
        """Return all runs, most-recent first."""
        cur = self._conn.execute(
            "SELECT id, run_at, period, budget, tickers_json "
            "FROM runs ORDER BY id DESC"
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def fetch_snapshots(self, run_id: int) -> list[dict]:
        """Return all ticker snapshots for a run, ordered by score desc."""
        cur = self._conn.execute(
            "SELECT * FROM ticker_snapshot "
            "WHERE run_id = ? ORDER BY score DESC",
            (run_id,)
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def fetch_price_history(self, run_id: int, ticker: str) -> list[dict]:
        """Return OHLCV rows for a specific ticker/run."""
        cur = self._conn.execute(
            "SELECT date, open, high, low, close, volume "
            "FROM price_history "
            "WHERE run_id = ? AND ticker = ? ORDER BY date",
            (run_id, ticker)
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def fetch_strategies(self, run_id: int,
                         ticker: str = "") -> list[dict]:
        """Return strategies for a run; optionally filter by ticker."""
        if ticker:
            cur = self._conn.execute(
                "SELECT * FROM strategies WHERE run_id = ? AND ticker = ?",
                (run_id, ticker)
            )
        else:
            cur = self._conn.execute(
                "SELECT * FROM strategies WHERE run_id = ?", (run_id,)
            )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()

    # ── Private insert helpers ────────────────────────────────────────────────

    def _insert_snapshot(self, cur, run_id: int,
                          result: AnalysisResult) -> None:
        ind = result.ind
        td  = result.td
        cur.execute("""
            INSERT INTO ticker_snapshot (
                run_id, ticker, short_name,
                price, rsi, macd_hist, bb_pct, bb_width, bb_upper, bb_lower,
                sma20, sma50, sma200, ema21, vwap, adx, atr, stoch_k,
                golden_cross, trend, score, score_detail,
                ret_1w, ret_1m, ret_3m, ret_6m, ret_1y, rs_vs_spy,
                vol_30d_ann, max_dd, sharpe_est,
                support, resistance, pct_from_50sma, pct_from_200sma, pct_from_vwap,
                pe_ttm, pe_fwd, peg, rev_growth, earnings_growth,
                debt_eq, market_cap, beta, sector,
                dividend_yield, week52_high, week52_low, analyst_target
            ) VALUES (
                ?,?,?, ?,?,?,?,?,?,?, ?,?,?,?,?,?,?,?,
                ?,?,?,?, ?,?,?,?,?,?, ?,?,?, ?,?,?,?,?,
                ?,?,?,?,?, ?,?,?,?, ?,?,?,?
            )""",
            (
                run_id, td.ticker, td.short_name,
                ind.price, ind.rsi, ind.macd_hist,
                ind.bb_pct, ind.bb_width, ind.bb_upper, ind.bb_lower,
                ind.sma20, ind.sma50, ind.sma200, ind.ema21, ind.vwap,
                ind.adx, ind.atr, ind.stoch_k,
                int(ind.golden_cross), ind.trend,
                ind.score, json.dumps(ind.score_detail),
                ind.ret_1w, ind.ret_1m, ind.ret_3m, ind.ret_6m, ind.ret_1y,
                result.rs_vs_spy,
                ind.vol_30d_ann, ind.max_dd, ind.sharpe_est,
                ind.support, ind.resistance,
                ind.pct_from_50sma, ind.pct_from_200sma, ind.pct_from_vwap,
                td.pe_ttm, td.pe_fwd, td.peg,
                td.rev_growth, td.earnings_growth,
                td.debt_eq, td.market_cap, td.beta, td.sector,
                td.dividend_yield, td.week52_high, td.week52_low,
                td.analyst_target,
            )
        )

    def _insert_price_history(self, cur, run_id: int,
                               result: AnalysisResult) -> None:
        df = result.td.ohlcv
        if df is None:
            return
        ticker = result.td.ticker
        rows = []
        for ts, row in df.iterrows():
            date_str = (ts.strftime("%Y-%m-%d")
                        if hasattr(ts, "strftime") else str(ts))
            rows.append((
                run_id, ticker, date_str,
                _safe(row, "open"),  _safe(row, "high"),
                _safe(row, "low"),   float(row["close"]),
                _safe(row, "volume"),
            ))
        cur.executemany(
            "INSERT INTO price_history "
            "(run_id, ticker, date, open, high, low, close, volume) "
            "VALUES (?,?,?,?,?,?,?,?)",
            rows
        )

    def _insert_strategies(self, cur, run_id: int,
                            result: AnalysisResult) -> None:
        ticker = result.td.ticker
        for s in result.cash_strats:
            cur.execute(
                "INSERT INTO strategies "
                "(run_id, ticker, kind, name, action, rationale, tips_json) "
                "VALUES (?,?,?,?,?,?,?)",
                (run_id, ticker, "cash",
                 s.name, s.action, s.rationale, json.dumps(s.tips))
            )
        if result.opt_strat:
            s = result.opt_strat
            cur.execute(
                "INSERT INTO strategies "
                "(run_id, ticker, kind, name, action, rationale, tips_json) "
                "VALUES (?,?,?,?,?,?,?)",
                (run_id, ticker, "options",
                 s.name, s.action, s.rationale, json.dumps(s.tips))
            )

    def _insert_options(self, cur, run_id: int,
                         result: AnalysisResult) -> None:
        if not result.opt_strat:
            return
        snap = result.opt_strat.snap
        cur.execute(
            "INSERT INTO options_snapshot "
            "(run_id, ticker, expiry, call_iv, put_iv, pc_ratio, error) "
            "VALUES (?,?,?,?,?,?,?)",
            (run_id, result.td.ticker,
             snap.expiry, snap.atm_call_iv, snap.atm_put_iv,
             snap.pc_ratio, snap.error)
        )


# ── Module-level helper ───────────────────────────────────────────────────────

def _safe(row, col: str) -> Optional[float]:
    """Return float value of a DataFrame cell, or None if missing/NaN."""
    try:
        v = row[col]
        return float(v) if v == v else None   # NaN check: NaN != NaN
    except (KeyError, TypeError):
        return None
