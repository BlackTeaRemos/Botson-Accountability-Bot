from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import text
from typing import Any
from collections.abc import Mapping, Sequence

from .migrations import metadata
from .models import Base

class Database:
    """SQLAlchemy database connection manager with session factory."""

    def __init__(self, path: str):
        """Initialize database connection.

        Args:
            path: Path to SQLite database file.
        """
        self._engine = create_engine(
            f"sqlite:///{path}",
            connect_args={
                "check_same_thread": False,
            },
            pool_pre_ping=True,
            echo=False,
        )

        def _set_sqlite_pragmas(dbapi_connection, connection_record):  # type: ignore[no-redef]
            try:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()
            except Exception:
                # Best-effort; do not block engine initialization
                pass

        event.listen(self._engine, "connect", _set_sqlite_pragmas)  # type: ignore[arg-type]

        self._session_factory = sessionmaker(
            bind=self._engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False
        )

        self.metadata = metadata  # Database metadata
        self.Base = Base  # Base class for models

    def _SetupConnection(self) -> None:
        """Set up SQLite pragmas for the database connection."""
        with self._engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA foreign_keys=ON"))
            conn.commit()

    def CreateTables(self) -> None:
        """Create all tables defined in metadata if they don't exist."""
        self._SetupConnection()
        self.Base.metadata.create_all(bind=self._engine)

    def GetSession(self) -> Session:
        """Get a new database session.

        Returns:
            SQLAlchemy session object.
        """
        return self._session_factory()

    def ExecuteRaw(self, sql: str, params: Mapping[str, Any] | Sequence[Any] | None = None) -> None:
        """Execute raw SQL

        Args:
            sql: Raw SQL string.
            params: Parameters for SQL query.
        """
        with self._engine.connect() as conn:
            if params is None:
                conn.execute(text(sql))
            else:
                conn.execute(text(sql), params)
            conn.commit()

    def QueryRaw(self, sql: str, params: Mapping[str, Any] | Sequence[Any] | None = None) -> list[tuple[Any, ...]]:
        """Execute raw SQL query and return results.

        Args:
            sql: Raw SQL string.
            params: Parameters for SQL query.

        Returns:
            List of result rows.
        """
        with self._engine.connect() as conn:
            if params is None:
                result = conn.execute(text(sql))
            else:
                result = conn.execute(text(sql), params)
            rows = result.fetchall()
            # SQLAlchemy returns Row objects; normalize to tuples for typing simplicity
            return [tuple(row) for row in rows]
