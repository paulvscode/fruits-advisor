"""Database engine and session factory."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models import Base

# SQLite for MVP — path: data/fruits_advisor.db (gitignored)
_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "fruits_advisor.db"
_DB_PATH.parent.mkdir(exist_ok=True)

engine = create_engine(f"sqlite:///{_DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    """Create all tables if they don't exist yet."""
    Base.metadata.create_all(engine)
