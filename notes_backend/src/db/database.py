import os
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session


class Base(DeclarativeBase):
    """SQLAlchemy Declarative Base for all models."""
    pass


def _get_database_url() -> str:
    """
    Resolve database URL from environment with a safe default.

    - Uses DATABASE_URL if present.
    - Defaults to SQLite file DB at ./notes.db for development.
    - Keeps Postgres-ready options by not altering non-sqlite URLs.
    """
    env_url: Optional[str] = os.getenv("DATABASE_URL")
    if env_url and env_url.strip():
        return env_url.strip()
    # Local dev default
    return "sqlite:///./notes.db"


def _engine_kwargs_for_url(url: str) -> dict:
    """
    Configure engine kwargs based on the database URL.

    For SQLite:
      - check_same_thread disabled for multi-threaded FastAPI workers
    """
    if url.startswith("sqlite:///") or url.startswith("sqlite://"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


# Create engine and session factory using SQLAlchemy 2.x style
DATABASE_URL = _get_database_url()
# Example default if env not set: sqlite:///./notes.db (file adjacent to app root)
engine = create_engine(DATABASE_URL, echo=False, future=True, **_engine_kwargs_for_url(DATABASE_URL))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)


# PUBLIC_INTERFACE
def get_db() -> Generator[Session, None, None]:
    """Yield a database session and ensure it is closed after use."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
