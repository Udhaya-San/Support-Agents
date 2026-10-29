"""
core/db.py  -  connects to the database and creates the tables.

Run once from the project root to create support.db:
    python -m core.db
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from core.models import Base

load_dotenv(override=True)

# Default = a SQLite file called support.db in the folder you run from.
# Later, for PostgreSQL, you only change this line in .env:
#   DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/support
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///support.db")

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)

# A "session" is one conversation with the database. expire_on_commit=False keeps
# objects readable after saving them.
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_session():
    """Use like:  with get_session() as s:  s.add(...); s.commit()"""
    return SessionLocal()


def init_db():
    """Create all tables if they do not exist yet (safe to run many times)."""
    Base.metadata.create_all(engine)


if __name__ == "__main__":
    init_db()
    print("Database:", DATABASE_URL)
    print("Tables created:", inspect(engine).get_table_names())
