from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, DateTime, Float, Text, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.sql import text
import os

# Import models for metadata
from .models import Base

# Use metadata from models
metadata = Base.metadata
def generate_migration_sql() -> str:
    """Generate SQL DDL statements from SQLAlchemy metadata.
    
    Returns:
        Combined SQL string with all CREATE TABLE and CREATE INDEX statements.
    """
    from sqlalchemy.schema import CreateTable, CreateIndex
    
    sql_statements: list[str] = []
    
    # Generate CREATE TABLE statements
    for table in metadata.sorted_tables:
        stmt = str(CreateTable(table).compile(create_engine('sqlite://'))).strip()
        if not stmt.endswith(";"):
            stmt += ";"
        sql_statements.append(stmt)
    
    # Generate CREATE INDEX statements for indexes not covered by table constraints
    for table in metadata.sorted_tables:
        for index in table.indexes:
            if not index._column_flag:  # Skip implicit indexes from unique constraints
                stmt = str(CreateIndex(index).compile(create_engine('sqlite://'))).strip()
                if not stmt.endswith(";"):
                    stmt += ";"
                sql_statements.append(stmt)
    
    return '\n'.join(sql_statements)

MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        generate_migration_sql(),
    ),
]


def ensure_migrated(database_path: str) -> None:
    """Ensure the database is migrated to the latest schema version.

    Connects to the database, checks the current schema version, and applies
    any pending migrations by executing the SQL statements.

    Args:
        database_path: Path to the SQLite database file.
    """
    # Create parent directory if necessary so SQLite can create the DB file
    parent_dir = os.path.dirname(os.path.abspath(database_path))
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)

    # Create engine for migrations
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={
            "check_same_thread": False,
        }
    )
    
    # Set up SQLite pragmas
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        conn.commit()

    # Run migrations inside a single transaction to keep state consistent
    with engine.begin() as connection:
        connection.execute(text(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ))

        result = connection.execute(text(
            "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
        ))
        row = result.fetchone()
        current_version = row[0] if row else 0

        # Apply pending migrations
        for migration_version, migration_sql in MIGRATIONS:
            if migration_version > current_version and migration_sql.strip():
                # Split and execute SQL statements
                sql_statements = [stmt.strip() for stmt in migration_sql.strip().split(";") if stmt.strip()]
                for sql_statement in sql_statements:
                    connection.execute(text(sql_statement))

                # Record migration completion (use named bind parameter for SQLAlchemy 2.x)
                connection.execute(
                    text("INSERT INTO schema_version(version) VALUES (:version)"),
                    {"version": migration_version},
                )
