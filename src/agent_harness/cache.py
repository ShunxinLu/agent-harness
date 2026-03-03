"""
Harness Cache - Test result caching with DuckDB persistence.

Design Principle: Stores test results and traces ONLY - no file hashing.
Native framework caching handles test selection.

DuckDB Synergy: Uses the same DuckDB instance as TraceStore for cross-analysis.
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

import duckdb


class CachedTestResult(BaseModel):
    """A cached test result."""
    id: str
    project: str
    test_name: str
    status: str  # passed, failed, skipped, error
    duration_ms: float
    error_message: Optional[str] = None
    run_id: str
    timestamp: datetime

    class Config:
        arbitrary_types_allowed = True


class CacheStats(BaseModel):
    """Cache statistics."""
    total_runs: int
    total_tests: int
    projects: list[str]
    oldest_run: Optional[datetime] = None
    newest_run: Optional[datetime] = None


class HarnessCache:
    """
    DuckDB-backed cache for test results.

    Shares DuckDB instance with TraceStore for cross-analysis queries.
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize cache.

        Args:
            db_path: Path to DuckDB file. Uses in-memory if not specified.
        """
        self.db_path = db_path or ":memory:"

        if self.db_path != ":memory:":
            db_file = Path(self.db_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)

        self._conn = duckdb.connect(self.db_path)
        self._init_schema()

    def _init_schema(self):
        """Initialize the cache table schema."""
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS test_results (
                id VARCHAR PRIMARY KEY,
                project VARCHAR,
                test_name VARCHAR,
                status VARCHAR,
                duration_ms DOUBLE,
                error_message VARCHAR,
                run_id VARCHAR,
                timestamp TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes for common queries
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_results_project ON test_results(project)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_results_run_id ON test_results(run_id)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_results_timestamp ON test_results(timestamp)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_results_status ON test_results(status)")

        # Create run_history table for tracking runs
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS run_history (
                run_id VARCHAR PRIMARY KEY,
                project VARCHAR,
                total_tests INTEGER,
                passed INTEGER,
                failed INTEGER,
                skipped INTEGER,
                duration_ms DOUBLE,
                timestamp TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_run_history_project ON run_history(project)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_run_history_timestamp ON run_history(timestamp)")

    def store_run(self, project: str, run_id: str, results: list[dict], duration_ms: float = 0):
        """
        Store results from a test run.

        Args:
            project: Project name
            run_id: Unique run identifier
            results: List of test result dicts with name, status, duration, error
            duration_ms: Total run duration in milliseconds
        """
        run_uuid = run_id or str(uuid.uuid4())
        now = datetime.now()

        passed = sum(1 for r in results if r.get("status") == "passed")
        failed = sum(1 for r in results if r.get("status") == "failed")
        skipped = sum(1 for r in results if r.get("status") == "skipped")

        # Store run summary
        self._conn.execute("""
            INSERT INTO run_history (run_id, project, total_tests, passed, failed, skipped, duration_ms, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (run_uuid, project, len(results), passed, failed, skipped, duration_ms, now))

        # Store individual test results
        for result in results:
            test_id = str(uuid.uuid4())
            test_name = result.get("name", "unknown")
            status = result.get("status", "unknown")
            duration = result.get("duration", 0) * 1000  # Convert to ms
            error_msg = None

            if result.get("error"):
                error_msg = result["error"].get("message") if isinstance(result["error"], dict) else str(result["error"])

            self._conn.execute("""
                INSERT INTO test_results (id, project, test_name, status, duration_ms, error_message, run_id, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (test_id, project, test_name, status, duration, error_msg, run_uuid, now))

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        result = self._conn.execute("SELECT COUNT(DISTINCT run_id) FROM run_history").fetchone()
        total_runs = result[0] if result else 0

        result = self._conn.execute("SELECT COUNT(*) FROM test_results").fetchone()
        total_tests = result[0] if result else 0

        result = self._conn.execute("SELECT DISTINCT project FROM run_history ORDER BY project").fetchall()
        projects = [r[0] for r in result]

        result = self._conn.execute("SELECT MIN(timestamp), MAX(timestamp) FROM run_history").fetchone()
        oldest = result[0] if result and result[0] else None
        newest = result[1] if result and result[1] else None

        return CacheStats(
            total_runs=total_runs,
            total_tests=total_tests,
            projects=projects,
            oldest_run=oldest,
            newest_run=newest,
        )

    def get_trend(self, project: str, limit: int = 10) -> list[dict]:
        """
        Get test trend over time for a project.

        Returns last N runs with pass/fail counts.
        """
        results = self._conn.execute("""
            SELECT run_id, total_tests, passed, failed, skipped, timestamp
            FROM run_history
            WHERE project = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (project, limit)).fetchall()

        return [
            {
                "run_id": r[0],
                "total": r[1],
                "passed": r[2],
                "failed": r[3],
                "skipped": r[4],
                "timestamp": r[5].isoformat() if r[5] else None,
            }
            for r in results
        ]

    def get_last_failed(self, project: str) -> list[str]:
        """
        Get list of tests that failed in the most recent run.

        Used for --last-failed functionality.
        """
        # Get the most recent run_id for this project
        result = self._conn.execute("""
            SELECT run_id FROM run_history
            WHERE project = ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (project,)).fetchone()

        if not result:
            return []

        run_id = result[0]

        # Get failed tests from that run
        failed = self._conn.execute("""
            SELECT test_name FROM test_results
            WHERE run_id = ? AND status = 'failed'
        """, (run_id,)).fetchall()

        return [r[0] for r in failed]

    def get_errors(self, project: Optional[str] = None, limit: int = 50) -> list[dict]:
        """Get recent error messages."""
        where_clause = "WHERE project = ?" if project else ""
        params = (project,) if project else ()

        results = self._conn.execute(f"""
            SELECT test_name, error_message, timestamp
            FROM test_results
            {where_clause} AND error_message IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT ?
        """, (*params, limit)).fetchall()

        return [
            {
                "test_name": r[0],
                "error_message": r[1],
                "timestamp": r[2].isoformat() if r[2] else None,
            }
            for r in results
        ]

    def clear(self, project: Optional[str] = None):
        """Clear cache, optionally for a specific project only."""
        if project:
            self._conn.execute("DELETE FROM test_results WHERE project = ?", (project,))
            self._conn.execute("DELETE FROM run_history WHERE project = ?", (project,))
        else:
            self._conn.execute("DELETE FROM test_results")
            self._conn.execute("DELETE FROM run_history")

    def close(self):
        """Close the database connection."""
        self._conn.close()


# Global cache instance
_default_cache: Optional[HarnessCache] = None


def get_default_cache(db_path: Optional[str] = None) -> HarnessCache:
    """Get or create default cache instance.

    Uses persistent storage in ~/.harness/data/harness.duckdb
    """
    global _default_cache

    if db_path is None:
        # Use persistent storage
        data_dir = Path.home() / ".harness" / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(data_dir / "harness.duckdb")

    if _default_cache is None:
        _default_cache = HarnessCache(db_path)
    return _default_cache
