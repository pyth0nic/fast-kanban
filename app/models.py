"""Domain models for the kanban board, expressed with Pydantic/SQLModel."""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field as PydanticField
from sqlalchemy import JSON, Column
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


class TaskPriority(str, Enum):
    """Sort order used by task routing and SLA windows."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Task(SQLModel, table=True):
    """A single kanban card persisted in SQLite."""

    __tablename__ = "task"

    id: Optional[int] = Field(default=None, primary_key=True)
    workspace_id: str = Field(default="", index=True)
    assignee_id: Optional[str] = Field(default=None, index=True)
    title: str = Field(index=True)
    description: str = ""
    status: TaskStatus = Field(default=TaskStatus.BACKLOG, index=True)
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM, index=True)
    due_at: Optional[datetime] = Field(default=None, index=True)
    labels: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    external_ref: Optional[str] = Field(default=None, index=True)
    version: int = Field(default=1, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class TaskOutboxStatus(str, Enum):
    """Delivery state for task lifecycle events stored in the outbox."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class TaskOutboxEvent(SQLModel, table=True):
    """Versioned task lifecycle events retained for replay and delivery."""

    __tablename__ = "task_outbox_event"

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: int = Field(index=True)
    version: int = Field(default=1, index=True)
    event_type: str = Field(index=True)
    payload: str = ""
    status: TaskOutboxStatus = Field(default=TaskOutboxStatus.PENDING, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    delivered_at: Optional[datetime] = Field(default=None)


class TaskIdempotencyRecord(SQLModel, table=True):
    """Records idempotent mutation requests to block conflicting retries."""

    __tablename__ = "task_idempotency_record"

    id: Optional[int] = Field(default=None, primary_key=True)
    scope: str = Field(index=True)
    key: str = Field(index=True)
    request_hash: str = Field(index=True)
    response_status: int = 200
    response_body: str = ""
    created_at: datetime = Field(default_factory=utcnow)


TaskEvent = TaskOutboxEvent


class TaskCreate(BaseModel):
    """Payload for creating a new task."""

    workspace_id: str = ""
    assignee_id: Optional[str] = None
    title: str
    description: str = ""
    status: TaskStatus = TaskStatus.BACKLOG
    priority: TaskPriority = TaskPriority.MEDIUM
    due_at: Optional[datetime] = None
    labels: list[str] = PydanticField(default_factory=list)
    external_ref: Optional[str] = None


class TaskUpdate(BaseModel):
    """Payload for partially updating an existing task."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: Optional[str] = None
    assignee_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    due_at: Optional[datetime] = None
    labels: Optional[list[str]] = None
    external_ref: Optional[str] = None


class TaskRead(BaseModel):
    """Representation of a task returned to API clients."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: str
    assignee_id: Optional[str]
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    due_at: Optional[datetime]
    labels: list[str]
    external_ref: Optional[str]
    version: int
    created_at: datetime
    updated_at: datetime


class TaskOutboxEventRead(BaseModel):
    """Read model for the deferred task event stream."""

    id: int
    task_id: int
    version: int
    event_type: str
    payload: str
    status: TaskOutboxStatus
    created_at: datetime
    delivered_at: Optional[datetime]
