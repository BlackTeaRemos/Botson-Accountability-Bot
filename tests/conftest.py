import os
import pytest  # type: ignore

# Ensure headless matplotlib backend for image-generation tests
try:
    import matplotlib
    matplotlib.use("Agg")  # type: ignore[attr-defined]
except Exception:
    pass

from src.db.migrations import ensure_migrated
from src.db.connection import Database
from typing import Iterator, Any
from sqlalchemy.orm import Session
from src.db.models import Channel
from src.services.persistence import PersistenceService


@pytest.fixture()  # type: ignore
def temp_db_path(tmp_path_factory: Any) -> Iterator[str]:
    # Create a unique temporary database path per test session
    tmpdir = tmp_path_factory.mktemp("db")
    db_path = os.path.join(str(tmpdir), "test.db")
    yield db_path
    # Cleanup file after test (SQLite creates -wal/-shm files as well)
    for suffix in ("", "-wal", "-shm"):
        p = db_path + suffix
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

@pytest.fixture()  # type: ignore
def db(temp_db_path: str) -> Database:
    # Run migrations and return Database instance
    ensure_migrated(temp_db_path)
    database = Database(temp_db_path)
    # Ensure ORM create_all is idempotent
    database.create_tables()
    return database


@pytest.fixture()  # type: ignore
def storage(db: Database) -> PersistenceService:
    """Persistence service bound to the temporary test database."""
    return PersistenceService(db)


@pytest.fixture()  # type: ignore
def seed_channel(db: Database) -> int:
    """Insert and return a test channel discord id that is active."""
    session: Session = db.get_session()
    try:
        if not session.query(Channel).filter(Channel.discord_channel_id == "12345").first():
            session.add(Channel(discord_channel_id="12345", registered_by="tester", active=True))
            session.commit()
        return 12345
    finally:
        session.close()
