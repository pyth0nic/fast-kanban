"""Functional core/imperative shell for task persistence and business rules."""
from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import String, func
from sqlmodel import Session, select

from app.models import (
    Task,
    TaskCreate,
    TaskEvent,
    TaskOutboxStatus,
    TaskPriority,
    TaskStatus,
    TaskUpdate,
    utcnow,
)

# Ordered progression of kanban columns. Pure data, drives `next_status`.
_STATUS_FLOW: tuple[TaskStatus, ...] = (
    TaskStatus.BACKLOG,
    TaskStatus.TODO,
    TaskStatus.IN_PROGRESS,
    TaskStatus.DONE,
)


def next_status(status: TaskStatus) -> TaskStatus:
    """Return the next column a task moves into, or the same status if already done.

    Pure function: given a status, always returns the same result.
    """
    if status == TaskStatus.DONE:
        return TaskStatus.DONE
    return _STATUS_FLOW[_STATUS_FLOW.index(status) + 1]


def task_etag(task: Task) -> str:
    """Return an ETag value for a task version."""
    return f'W/"{task.version}"'


def matches_etag(task: Task, etag_header: Optional[str]) -> bool:
    """Return whether an incoming ETag matches the task's version."""
    if etag_header is None or etag_header == "*":
        return True
    normalized = etag_header.replace("W/", "").strip()
    return normalized in {f'"{task.version}"', str(task.version)}


def compute_changes(changes: TaskUpdate) -> dict:
    """Return the attribute overrides implied by an update payload.

    Pure function: given the same input, always returns the same dict and
    has no side effects. ``updated_at`` is always refreshed on real changes.
    """
    data = changes.model_dump(exclude_unset=True, exclude_none=True)
    if data:
        data["updated_at"] = utcnow()
    return data


def _task_event_payload(task: Task, event_type: str) -> str:
    payload = {
        "task_id": task.id,
        "workspace_id": task.workspace_id,
        "event_type": event_type,
        "version": task.version,
        "status": task.status.value,
        "priority": task.priority.value,
        "updated_at": task.updated_at.isoformat(),
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _enqueue_outbox_event(session: Session, task: Task, event_type: str) -> TaskEvent:
    event = TaskEvent(
        task_id=task.id,
        version=task.version,
        event_type=event_type,
        payload=_task_event_payload(task, event_type),
        status=TaskOutboxStatus.PENDING,
    )
    session.add(event)
    return event


def create_task(session: Session, payload: TaskCreate) -> Task:
    """Persist and return a brand new task."""
    task = Task(**payload.model_dump())
    task.version = 1
    task.created_at = utcnow()
    task.updated_at = task.created_at
    session.add(task)
    session.flush()
    _enqueue_outbox_event(session, task, "task.created")
    session.commit()
    session.refresh(task)
    return task


def list_tasks(
    session: Session,
    status: Optional[TaskStatus] = None,
    workspace_id: Optional[str] = None,
    assignee_id: Optional[str] = None,
    priority: Optional[TaskPriority] = None,
    labels: Optional[list[str]] = None,
    due_after: Optional[datetime] = None,
    due_before: Optional[datetime] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> Sequence[Task]:
    """Return tasks, optionally filtered by column and metadata."""
    statement = select(Task)
    if status is not None:
        statement = statement.where(Task.status == status)
    if workspace_id is not None:
        statement = statement.where(Task.workspace_id == workspace_id)
    if assignee_id is not None:
        statement = statement.where(Task.assignee_id == assignee_id)
    if priority is not None:
        statement = statement.where(Task.priority == priority)
    if labels:
        for label in labels:
            statement = statement.where(Task.labels.cast(String).like(f'%"{label}"%'))
    if due_after is not None:
        statement = statement.where((Task.due_at.is_not(None)) & (Task.due_at >= due_after))
    if due_before is not None:
        statement = statement.where((Task.due_at.is_not(None)) & (Task.due_at <= due_before))
    statement = statement.order_by(Task.created_at)
    if offset:
        statement = statement.offset(offset)
    if limit is not None:
        statement = statement.limit(limit)
    return session.exec(statement).all()


def get_task(session: Session, task_id: int) -> Optional[Task]:
    """Return a single task by id, or ``None`` if it does not exist."""
    return session.get(Task, task_id)


def update_task(session: Session, task: Task, changes: TaskUpdate) -> Task:
    """Apply partial updates to a task and persist the result."""
    data = compute_changes(changes)
    if not data:
        return task
    for field, value in data.items():
        if field == "updated_at":
            continue
        setattr(task, field, value)
    task.version = (task.version or 0) + 1
    task.updated_at = utcnow()
    session.add(task)
    session.flush()
    _enqueue_outbox_event(session, task, "task.updated")
    session.commit()
    session.refresh(task)
    return task


def progress_task(session: Session, task: Task) -> Task:
    """Move a task to the next kanban column and persist the result."""
    return update_task(session, task, TaskUpdate(status=next_status(task.status)))


def delete_task(session: Session, task: Task) -> None:
    """Remove a task from the database."""
    task.version = (task.version or 0) + 1
    session.flush()
    _enqueue_outbox_event(session, task, "task.deleted")
    session.delete(task)
    session.commit()


def list_outbox_events(session: Session, cursor: int = 0, limit: int = 25) -> list[TaskEvent]:
    """Return pending or recently emitted outbox entries after a cursor."""
    statement = select(TaskEvent).where(TaskEvent.id > cursor).order_by(TaskEvent.id).limit(limit)
    return session.exec(statement).all()


def get_task_events(session: Session, task_id: int) -> Sequence[TaskEvent]:
    """Return the lifecycle events recorded for a task."""
    return session.exec(select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.id)).all()
