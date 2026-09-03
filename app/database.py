"""Database engine and session management for the SQLite-backed kanban board."""
from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

settings = get_settings()

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=settings.database_echo, connect_args=_connect_args)


def init_db() -> None:
    """Create database tables if they do not already exist."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """Yield a database session for use as a FastAPI dependency."""
    with Session(engine) as session:
        yield session
