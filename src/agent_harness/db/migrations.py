"""Alembic migration helpers for harness persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def build_db_url(db_path: Optional[str] = None) -> str:
    """Build a SQLAlchemy URL for the harness DuckDB database path."""
    if db_path:
        target = Path(db_path).expanduser().resolve()
    else:
        target = Path.home() / ".harness" / "data" / "harness.duckdb"
    return f"duckdb:///{target}"


def run_migrations(
    revision: str = "head",
    db_url: Optional[str] = None,
    db_path: Optional[str] = None,
) -> None:
    """
    Apply Alembic migrations to the selected database.

    Args:
        revision: Alembic revision target (default: head).
        db_url: Explicit SQLAlchemy URL override.
        db_path: Optional DuckDB path used when db_url is not set.
    """
    try:
        from alembic import command
        from alembic.config import Config
    except ImportError as exc:
        raise RuntimeError(
            "Alembic/SQLAlchemy dependencies are not installed. "
            "Install with: pip install -e '.[migrations]'"
        ) from exc

    repo_root = Path(__file__).resolve().parents[3]
    alembic_ini = repo_root / "alembic.ini"
    if not alembic_ini.exists():
        raise RuntimeError(f"Alembic config not found: {alembic_ini}")

    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(repo_root / "alembic"))
    config.set_main_option("sqlalchemy.url", db_url or build_db_url(db_path))
    command.upgrade(config, revision)
