"""SQLite connection handling and versioned schema initialization."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
SCHEMA_VERSION = 7

BUSY_TIMEOUT_MS = 5000


def utc_now_iso() -> str:
    """Canonical internal timestamp: UTC ISO-8601 (displayed as Jalali in UI)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection with the project's durability/concurrency settings."""
    connection = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_MS / 1000)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    return connection


def init_db(db_path: str | Path) -> None:
    """Apply pending migrations in order. Idempotent; records each version."""
    connection = connect(db_path)
    try:
        # ensure the version table exists before consulting it
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL, applied_at TEXT NOT NULL)"
        )
        applied = {
            row["version"]
            for row in connection.execute("SELECT version FROM schema_version").fetchall()
        }
        # v1 is the base schema (kept as schema.sql for historical clarity)
        migrations: list[tuple[int, Path]] = [(1, SCHEMA_PATH)]
        for path in sorted(MIGRATIONS_DIR.glob("v*.sql")):
            version = int(path.name.split("__")[0][1:])
            migrations.append((version, path))
        for version, path in migrations:
            if version in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            # v5/v6 rebuild tables and need FK checks off; that pragma is a
            # no-op inside a transaction, so set it outside and restore after.
            fk_off = "foreign_keys" in sql.lower()
            if fk_off:
                connection.execute("PRAGMA foreign_keys=OFF")
            try:
                connection.executescript(
                    "BEGIN IMMEDIATE;\n"
                    + sql
                    + "\nINSERT INTO schema_version (version, applied_at) VALUES "
                    + f"({version}, '{utc_now_iso()}');\nCOMMIT;"
                )
            except BaseException:
                connection.rollback()
                raise
            finally:
                if fk_off:
                    connection.execute("PRAGMA foreign_keys=ON")
    finally:
        connection.close()
