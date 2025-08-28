from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, DateTime, Float, Text, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.sql import text

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
    
    sql_statements = []
    
    # Generate CREATE TABLE statements
    for table in metadata.sorted_tables:
        sql_statements.append(str(CreateTable(table).compile(create_engine('sqlite://'))))
    
    # Generate CREATE INDEX statements for indexes not covered by table constraints
    for table in metadata.sorted_tables:
        for index in table.indexes:
            if not index._column_flag:  # Skip implicit indexes from unique constraints
                sql_statements.append(str(CreateIndex(index).compile(create_engine('sqlite://'))))
    
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
    # Create engine for migrations
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={
            "check_same_thread": False,
        }
    )
    
    # Set up SQLite pragmas
    with engine.connect() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.commit()
    
    with engine.connect() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER NOT NULL, 
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        connection.commit()
        
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
                
                # Record migration completion
                connection.execute(text(
                    "INSERT INTO schema_version(version) VALUES (?)"
                ), (migration_version,))
                connection.commit()
