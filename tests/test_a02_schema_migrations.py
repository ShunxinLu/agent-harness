import sqlite3
from pathlib import Path

from harness.cache import HarnessCache
from harness.db import build_db_url, run_migrations
from harness.db.models import RunHistory, TestResultRecord, TraceRecord
from harness.tracing import TraceStore


def _duckdb_columns(cache: HarnessCache, table: str) -> set[str]:
    rows = cache._repo.fetchall(f"PRAGMA table_info('{table}')")
    return {row[1] for row in rows}


def test_sqlalchemy_models_match_runtime_schema_columns(tmp_path: Path):
    db_path = tmp_path / "harness.duckdb"
    cache = HarnessCache(str(db_path))
    store = TraceStore(str(db_path))

    expected_test_results = {col.name for col in TestResultRecord.__table__.columns}
    expected_run_history = {col.name for col in RunHistory.__table__.columns}
    expected_traces = {col.name for col in TraceRecord.__table__.columns}

    actual_test_results = _duckdb_columns(cache, "test_results")
    actual_run_history = _duckdb_columns(cache, "run_history")
    actual_traces = _duckdb_columns(cache, "traces")

    assert expected_test_results.issubset(actual_test_results)
    assert expected_run_history.issubset(actual_run_history)
    assert expected_traces.issubset(actual_traces)

    cache.close()
    store.close()


def test_migration_smoke_upgrade_head_sqlite(tmp_path: Path):
    db_file = tmp_path / "harness_schema.sqlite"
    db_url = f"sqlite:///{db_file}"
    run_migrations(db_url=db_url, revision="head")

    with sqlite3.connect(db_file) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert {"test_results", "run_history", "traces", "alembic_version"}.issubset(tables)

        run_history_columns = {
            row[1] for row in conn.execute("PRAGMA table_info('run_history')").fetchall()
        }
        assert "parent_run_id" in run_history_columns


def test_build_db_url_defaults_to_harness_duckdb():
    db_url = build_db_url()
    assert db_url.startswith("duckdb:///")
    assert db_url.endswith("harness.duckdb")
