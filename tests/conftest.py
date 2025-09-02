import os
import tempfile
import shutil
import pytest

from src.db.migrations import ensure_migrated
from src.db.connection import Database

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
    ensure_migrated(temp_db_path)
    database = Database(temp_db_path)
    # Ensure ORM create_all is idempotent
    database.create_tables()
    return database
