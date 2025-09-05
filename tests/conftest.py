import os
import tempfile
import shutil
import pytest

from src.db.migrations import EnsureMigrated
from src.db.connection import Database
from src.db.models import Channel
from src.services.persistence import PersistenceService
from sqlalchemy.orm import Session

@pytest.fixture()
def temp_db_path(tmp_path_factory: pytest.TempPathFactory):
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

@pytest.fixture()
def db(temp_db_path: str):
    # Run migrations and return Database instance
    EnsureMigrated(temp_db_path)
    database = Database(temp_db_path)
    # Ensure ORM create_all is idempotent
    database.CreateTables()
    return database


@pytest.fixture()  # type: ignore
def storage(db: Database) -> PersistenceService:
    """Persistence service bound to the temporary test database."""
    return PersistenceService(db)


@pytest.fixture()  # type: ignore
def seed_channel(db: Database) -> int:
    """Insert and return a test channel discord id that is active."""
    session: Session = db.GetSession()
    try:
        if not session.query(Channel).filter(Channel.discord_channel_id == "12345").first():
            session.add(Channel(discord_channel_id="12345", registered_by="tester", active=True))
            session.commit()
        return 12345
    finally:
        session.close()
