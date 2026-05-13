"""
tests/test_database.py
───────────────────────
Integration tests for DatabaseManager.
Uses an in-memory SQLite database (:memory:) — no files created on disk.
"""

import json
import pytest

from semisector.database        import DatabaseManager
from semisector.indicators      import IndicatorEngine
from semisector.models          import AnalysisResult
from semisector.strategy_engine import StrategyEngine


BUDGET = 10_000


@pytest.fixture
def db(tmp_path):
    """Fresh DatabaseManager backed by a temp file; closed after each test."""
    path = str(tmp_path / "test.db")
    manager = DatabaseManager(path)
    yield manager
    manager.close()


@pytest.fixture
def analysis_result(ticker_data_nvda, indicator_nvda):
    engine = StrategyEngine(ticker_data_nvda, indicator_nvda,
                            BUDGET, show_options=False)
    cash, opt = engine.evaluate()
    return AnalysisResult(
        td=ticker_data_nvda, ind=indicator_nvda,
        cash_strats=cash, opt_strat=opt,
        rs_vs_spy=12.5,
    )


class TestDatabaseManager:

    def test_save_run_returns_int(self, db):
        run_id = db.save_run("1y", BUDGET, ["NVDA", "AMD"])
        assert isinstance(run_id, int) and run_id >= 1

    def test_multiple_runs_incrementing_ids(self, db):
        id1 = db.save_run("1y", BUDGET, ["NVDA"])
        id2 = db.save_run("6mo", BUDGET, ["AMD"])
        assert id2 > id1

    def test_list_runs_most_recent_first(self, db):
        db.save_run("1y",  BUDGET, ["NVDA"])
        db.save_run("6mo", BUDGET, ["AMD"])
        runs = db.list_runs()
        assert len(runs) == 2
        assert runs[0]["id"] > runs[1]["id"]   # most recent first

    def test_save_and_fetch_snapshot(self, db, analysis_result):
        run_id = db.save_run("1y", BUDGET, ["NVDA"])
        db.save_result(run_id, analysis_result)

        snaps = db.fetch_snapshots(run_id)
        assert len(snaps) == 1
        snap = snaps[0]
        assert snap["ticker"] == "NVDA"
        assert isinstance(snap["score"], int)
        assert snap["score"] >= 0

    def test_score_detail_is_valid_json(self, db, analysis_result):
        run_id = db.save_run("1y", BUDGET, ["NVDA"])
        db.save_result(run_id, analysis_result)

        snap = db.fetch_snapshots(run_id)[0]
        detail = json.loads(snap["score_detail"])
        assert isinstance(detail, dict)

    def test_price_history_row_count(self, db, analysis_result):
        run_id = db.save_run("1y", BUDGET, ["NVDA"])
        db.save_result(run_id, analysis_result)

        rows = db.fetch_price_history(run_id, "NVDA")
        assert len(rows) == 260   # synthetic df has 260 rows

    def test_price_history_has_expected_columns(self, db, analysis_result):
        run_id = db.save_run("1y", BUDGET, ["NVDA"])
        db.save_result(run_id, analysis_result)

        row = db.fetch_price_history(run_id, "NVDA")[0]
        for col in ("date", "open", "high", "low", "close", "volume"):
            assert col in row

    def test_strategies_saved(self, db, analysis_result):
        run_id = db.save_run("1y", BUDGET, ["NVDA"])
        db.save_result(run_id, analysis_result)

        strats = db.fetch_strategies(run_id, "NVDA")
        assert len(strats) >= 1
        assert all(s["kind"] in ("cash", "options") for s in strats)

    def test_strategies_tips_are_valid_json(self, db, analysis_result):
        run_id = db.save_run("1y", BUDGET, ["NVDA"])
        db.save_result(run_id, analysis_result)

        for s in db.fetch_strategies(run_id, "NVDA"):
            tips = json.loads(s["tips_json"])
            assert isinstance(tips, list)

    def test_context_manager(self, tmp_path, analysis_result):
        path   = str(tmp_path / "ctx.db")
        run_id_store = []
        with DatabaseManager(path) as db:
            run_id = db.save_run("1y", BUDGET, ["NVDA"])
            db.save_result(run_id, analysis_result)
            run_id_store.append(run_id)

        # Re-open and verify data persisted
        with DatabaseManager(path) as db:
            snaps = db.fetch_snapshots(run_id_store[0])
            assert len(snaps) == 1

    def test_rs_vs_spy_persisted(self, db, analysis_result):
        run_id = db.save_run("1y", BUDGET, ["NVDA"])
        db.save_result(run_id, analysis_result)

        snap = db.fetch_snapshots(run_id)[0]
        assert abs(snap["rs_vs_spy"] - 12.5) < 0.01
