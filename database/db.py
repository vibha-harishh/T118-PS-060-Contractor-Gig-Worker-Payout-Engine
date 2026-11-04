"""
Database Connection and Initialization Helper for SQLite
Project: T118-PS-060
Member 1: Payout and Earnings Module
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional, Union

import config


class DatabaseError(Exception):
    """Custom exception raised for database operational errors."""
    pass


def get_db_connection(db_path: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    """
    Creates and returns a connection to the SQLite database.

    Enforces on every connection:
    - Foreign key constraints (PRAGMA foreign_keys = ON)
    - Dictionary-like row access (sqlite3.Row)

    :param db_path: Optional path to the database file. Defaults to config.DATABASE_PATH.
    :return: sqlite3.Connection object
    """
    target_path = Path(db_path) if db_path else config.DATABASE_PATH

    # Ensure parent directory exists if using a file path (not :memory:)
    if str(target_path) != ":memory:":
        target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        conn = sqlite3.connect(str(target_path))
        conn.row_factory = sqlite3.Row

        # SQLite foreign keys are disabled by default; explicitly enable and verify
        conn.execute("PRAGMA foreign_keys = ON;")
        fk_enabled = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        if fk_enabled != 1:
            raise DatabaseError("Failed to enforce SQLite foreign key constraints.")

        return conn
    except sqlite3.Error as e:
        raise DatabaseError(f"Failed to connect to database at {target_path}: {e}") from e


@contextmanager
def db_session(db_path: Optional[Union[str, Path]] = None) -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for database transactions.

    Automatically commits if block succeeds, rolls back on exception,
    and always closes the connection upon exit.
    Preserves application-level exceptions while wrapping SQLite errors in DatabaseError.

    Example:
        with db_session() as conn:
            conn.execute("INSERT INTO partners ...")
    """
    conn = get_db_connection(db_path)
    try:
        yield conn
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        raise DatabaseError(f"Database error during transaction: {e}") from e
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(
    db_path: Optional[Union[str, Path]] = None,
    schema_file: Optional[Union[str, Path]] = None,
) -> None:
    """
    Initializes the SQLite database with the tables defined in schema.sql.

    :param db_path: Path to database file. Defaults to config.DATABASE_PATH.
    :param schema_file: Path to schema.sql file. Defaults to config.SCHEMA_PATH.
    """
    schema_target = Path(schema_file) if schema_file else config.SCHEMA_PATH

    if not schema_target.exists():
        raise DatabaseError(f"Schema file not found at: {schema_target}")

    try:
        with open(schema_target, "r", encoding="utf-8") as f:
            schema_sql = f.read()

        with db_session(db_path) as conn:
            conn.executescript(schema_sql)
    except sqlite3.Error as e:
        raise DatabaseError(f"Failed to initialize database schema: {e}") from e


def reset_db(db_path: Optional[Union[str, Path]] = None) -> None:
    """
    Utility to drop all tables and re-initialize the schema.
    Typically used in test fixtures or development resets.
    """
    drop_sql = """
    PRAGMA foreign_keys = OFF;
    DROP TABLE IF EXISTS weekly_earnings;
    DROP TABLE IF EXISTS complaints;
    DROP TABLE IF EXISTS tasks;
    DROP TABLE IF EXISTS partners;
    PRAGMA foreign_keys = ON;
    """
    with db_session(db_path) as conn:
        conn.executescript(drop_sql)

    init_db(db_path)
