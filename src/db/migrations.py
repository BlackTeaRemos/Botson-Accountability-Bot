"""Database schema migrations: ensure tables exist based on ORM models."""

import os
from sqlalchemy import create_engine
from .models import Base

# Expose metadata for migration compatibility
metadata = Base.metadata

def EnsureMigrated(database_path: str) -> None:
    """Ensure SQLite database file and all ORM tables exist."""
    # Ensure parent directory exists
    os.makedirs(os.path.dirname(os.path.abspath(database_path)), exist_ok=True)
    # Create engine with SQLite pragmas
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False}
    )
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
    # Create all tables defined in ORM models
    Base.metadata.create_all(engine)
    # Backwards-compatibility: ensure `settings` table has created_at and updated_at columns
    with engine.connect() as conn:
        try:
            # check if columns exist by selecting them
            conn.exec_driver_sql("SELECT created_at, updated_at FROM settings LIMIT 1")
        except Exception:
            # Add missing columns if the table exists but columns are absent
            try:
                conn.exec_driver_sql("ALTER TABLE settings ADD COLUMN created_at DATETIME DEFAULT (CURRENT_TIMESTAMP)")
            except Exception:
                pass
            try:
                conn.exec_driver_sql("ALTER TABLE settings ADD COLUMN updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP)")
            except Exception:
                pass
