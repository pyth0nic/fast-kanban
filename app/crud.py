"""Functional core/imperative shell for task persistence and business rules."""
from collections.abc import Sequence
from typing import Optional

from sqlmodel import Session, select

from app.models import Task, TaskCreate, TaskStatus, TaskUpdate, utcnow

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


def compute_changes(changes: TaskUpdate) -> dict:
    """Return the attribute overrides implied by an update payload.

    Pure function: given the same input, always returns the same dict and
    has no side effects. ``updated_at`` is always refreshed on real changes.
    """
    data = changes.model_dump(exclude_unset=True)
    if data:
        data["updated_at"] = utcnow()
    return data


def create_task(session: Session, payload: TaskCreate) -> Task:
    """Persist and return a brand new task."""
    task = Task(**payload.model_dump())
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def list_tasks(session: Session, status: Optional[TaskStatus] = None) -> Sequence[Task]:
    """Return all tasks, optionally filtered by kanban column."""
    statement = select(Task)
    if status is not None:
        statement = statement.where(Task.status == status)
    return session.exec(statement.order_by(Task.created_at)).all()


def get_task(session: Session, task_id: int) -> Optional[Task]:
    """Return a single task by id, or ``None`` if it does not exist."""
    return session.get(Task, task_id)


def update_task(session: Session, task: Task, changes: TaskUpdate) -> Task:
    """Apply partial updates to a task and persist the result."""
    for field, value in compute_changes(changes).items():
        setattr(task, field, value)
    session.add(task)
    session.commit()
    session.refresh(task)
    return task


def progress_task(session: Session, task: Task) -> Task:
    """Move a task to the next kanban column and persist the result."""
    return update_task(session, task, TaskUpdate(status=next_status(task.status)))


def delete_task(session: Session, task: Task) -> None:
    """Remove a task from the database."""
    session.delete(task)
    session.commit()
