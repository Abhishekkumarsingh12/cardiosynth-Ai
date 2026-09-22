"""SQLAlchemy engine and session. PostgreSQL when DATABASE_URL is set, else SQLite."""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine_url() -> str:
    settings = get_settings()
    if settings.database_url and settings.database_url.strip():
        return settings.database_url.strip()
    # SQLite fallback: file next to backend cwd
    db_path = Path(__file__).resolve().parent.parent / "cardiosynth.db"
    return f"sqlite:///{db_path}"


DATABASE_URL = _make_engine_url()

# SQLite needs check_same_thread=False for FastAPI
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create tables if they do not exist."""
    from app import models  # noqa: F401 — register models

    Base.metadata.create_all(bind=engine)
