"""
Shared DuckDB repository helpers.

This module centralizes low-level SQL execution so runtime modules can
avoid direct connection usage in operational code paths.
"""

from typing import Any, Optional

import duckdb


class DuckDBRepository:
    """Thin query helper around a DuckDB connection."""

    def __init__(self, connection: duckdb.DuckDBPyConnection):
        self._connection = connection

    def execute(self, sql: str, params: Optional[tuple[Any, ...]] = None):
        """Execute a SQL statement and return the cursor."""
        return self._connection.execute(sql, params or ())

    def fetchone(self, sql: str, params: Optional[tuple[Any, ...]] = None):
        """Execute a SQL query and return one row."""
        return self.execute(sql, params).fetchone()

    def fetchall(self, sql: str, params: Optional[tuple[Any, ...]] = None) -> list[tuple]:
        """Execute a SQL query and return all rows."""
        return self.execute(sql, params).fetchall()

    def fetchall_dict(self, sql: str, params: Optional[tuple[Any, ...]] = None) -> list[dict[str, Any]]:
        """Execute a SQL query and return rows as dictionaries."""
        result = self.execute(sql, params)
        columns = [desc[0] for desc in result.description]
        return [dict(zip(columns, row)) for row in result.fetchall()]

    def close(self):
        """Close the underlying DuckDB connection."""
        self._connection.close()

