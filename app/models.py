"""Domain models for the kanban board, expressed with Pydantic/SQLModel."""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    """Return the current UTC timestamp (used as a default factory)."""
    return datetime.now(timezone.utc)


class TaskStatus(str, Enum):
    """The kanban columns a task can progress through, in order."""

    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class Task(SQLModel, table=True):
    """A single kanban card persisted in SQLite."""

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    description: str = ""
    status: TaskStatus = Field(default=TaskStatus.BACKLOG, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class TaskCreate(BaseModel):
    """Payload for creating a new task."""

    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.BACKLOG


class TaskUpdate(BaseModel):
    """Payload for partially updating an existing task."""

    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None


class TaskRead(BaseModel):
    """Representation of a task returned to API clients."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
