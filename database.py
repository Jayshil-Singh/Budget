import os
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from contextlib import contextmanager
import config

# Ensure the database file is read-write if it's a local SQLite file (prevents read-only error on Streamlit Cloud)
if config.DATABASE_URL.startswith("sqlite:///"):
    db_filename = config.DATABASE_URL.replace("sqlite:///", "")
    if os.path.exists(db_filename):
        try:
            os.chmod(db_filename, 0o666)
        except Exception:
            pass

# Create SQLAlchemy engine
_engine_kwargs: dict = {}
_connect_args: dict = {}
if config.DATABASE_URL.startswith("sqlite"):
    _connect_args = {"check_same_thread": False, "timeout": 30}
elif config.DATABASE_URL.startswith("postgresql"):
    _connect_args = {"connect_timeout": 15, "sslmode": "require"}
    _engine_kwargs = {"pool_pre_ping": True, "pool_recycle": 300}

engine = create_engine(
    config.DATABASE_URL,
    connect_args=_connect_args,
    **_engine_kwargs,
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _run_sqlite_migrations():
    """Add new columns to existing SQLite DBs without Alembic."""
    if not config.DATABASE_URL.startswith("sqlite:///"):
        return
    import sqlite3
    db_path = config.DATABASE_URL.replace("sqlite:///", "")
    if not os.path.exists(db_path):
        return
    migrations = [
        ("users", "must_change_password", "INTEGER DEFAULT 0"),
        ("users", "ui_theme", "TEXT DEFAULT 'system'"),
        ("expenses", "logged_by_user_id", "INTEGER"),
        ("expenses", "attachment_note", "TEXT"),
    ]
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        for table, column, col_type in migrations:
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            except sqlite3.OperationalError:
                pass
        conn.commit()
    finally:
        conn.close()

@contextmanager
def get_db():
    """
    Context manager for database sessions.
    Ensures that sessions are closed after operations.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

@st.cache_resource
def init_db():
    """
    Initializes database tables.
    Importing models inside here avoids circular import issues.
    """
    from models.base import Base
    import models.auth
    import models.household
    import models.finance
    import models.budget
    import models.audit
    
    Base.metadata.create_all(bind=engine)
    _run_sqlite_migrations()

    # Auto-seed the database if newly created
    try:
        from seed import seed_data
        seed_data(skip_init=True)
    except Exception as e:
        print(f"[AUTO-SEED] Skipping or failed: {e}")
