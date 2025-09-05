from __future__ import annotations

from src.db.connection import Database


def test_execute_and_query_raw(tmp_path):
    db_path = tmp_path / "raw.sqlite"
    database = Database(str(db_path))
    # Create table and insert rows via raw SQL
    database.ExecuteRaw("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
    database.ExecuteRaw("INSERT INTO t (name) VALUES (:n)", {"n": "a"})
    database.ExecuteRaw("INSERT INTO t (name) VALUES (:n)", {"n": "b"})
    rows = database.QueryRaw("SELECT id, name FROM t ORDER BY id")
    assert rows == [(1, "a"), (2, "b")]
