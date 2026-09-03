"""Database engine and session management for the SQLite-backed kanban board."""
from collections.abc import Iterator

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

settings = get_settings()
_is_sqlite = settings.database_url.startswith("sqlite")

_connect_args = {"check_same_thread": False} if _is_sqlite else {}
engine = create_engine(settings.database_url, echo=settings.database_echo, connect_args=_connect_args)


if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _enable_wal_mode(dbapi_connection, _connection_record) -> None:
        """Switch SQLite to WAL journal mode for better read/write concurrency."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


def init_db() -> None:
    """Create database tables if they do not already exist."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """Yield a database session for use as a FastAPI dependency."""
    with Session(engine) as session:
        yield session
