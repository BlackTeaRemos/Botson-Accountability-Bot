"""Database schema migrations: ensure tables exist based on ORM models."""

import os
from sqlalchemy import create_engine
from .models import Base

metadata = Base.metadata

def EnsureMigrated(database_path: str) -> None:
    """Ensure SQLite database file and all ORM tables exist."""
    os.makedirs(os.path.dirname(os.path.abspath(database_path)), exist_ok=True)

    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False}
    )
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        
    Base.metadata.create_all(engine)
