from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql import text
from typing import Iterator
import os

# Import table definitions from migrations and models
from .migrations import metadata
from .models import Base

class Database:
    """SQLAlchemy database connection manager with session factory."""

    def __init__(self, path: str):
        """Initialize database connection.

        Args:
            path: Path to SQLite database file.
        """
        # Configure SQLite with WAL mode and foreign keys
        self._engine = create_engine(
            f"sqlite:///{path}",
            connect_args={
                "check_same_thread": False,  # Allow multi-threading
            },
            poolclass=StaticPool,  # Better for SQLite
            echo=False
        )

        self._session_factory = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False
        )

        self.metadata = metadata
        self.Base = Base

    def _setup_connection(self) -> None:
        """Set up SQLite pragmas for the database connection."""
        with self._engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA foreign_keys=ON"))
            conn.commit()

    def create_tables(self) -> None:
        """Create all tables defined in metadata if they don't exist."""
        self._setup_connection()
        self.Base.metadata.create_all(bind=self._engine)

    def get_session(self) -> Session:
        """Get a new database session.

        Returns:
            SQLAlchemy session object.
        """
        return self._session_factory()

    def execute_raw(self, sql: str, params: tuple = ()) -> None:
        """Execute raw SQL

        Args:
            sql: Raw SQL string.
            params: Parameters for SQL query.
        """
        with self._engine.connect() as conn:
            conn.execute(sql, params)
            conn.commit()

    def query_raw(self, sql: str, params: tuple = ()):
        """Execute raw SQL query and return results.

        Args:
            sql: Raw SQL string.
            params: Parameters for SQL query.

        Returns:
            List of result rows.
        """
        with self._engine.connect() as conn:
            result = conn.execute(sql, params)
            return result.fetchall()
