"""HTTP routes exposing the kanban task API."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app import crud
from app.database import get_session
from app.models import TaskCreate, TaskRead, TaskStatus, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _get_task_or_404(session: Session, task_id: int):
    task = crud.get_task(session, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, session: Session = Depends(get_session)) -> TaskRead:
    """Create a new kanban task."""
    return crud.create_task(session, payload)


@router.get("", response_model=list[TaskRead])
def list_tasks(
    status_filter: Optional[TaskStatus] = None, session: Session = Depends(get_session)
) -> list[TaskRead]:
    """List tasks, optionally filtered by kanban column."""
    return list(crud.list_tasks(session, status_filter))


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: int, session: Session = Depends(get_session)) -> TaskRead:
    """Fetch a single task by id."""
    return _get_task_or_404(session, task_id)


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: int, payload: TaskUpdate, session: Session = Depends(get_session)
) -> TaskRead:
    """Partially update a task's title, description, or status."""
    task = _get_task_or_404(session, task_id)
    return crud.update_task(session, task, payload)


@router.post("/{task_id}/progress", response_model=TaskRead)
def progress_task(task_id: int, session: Session = Depends(get_session)) -> TaskRead:
    """Advance a task to the next kanban column (backlog -> todo -> in_progress -> done)."""
    task = _get_task_or_404(session, task_id)
    return crud.progress_task(session, task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: int, session: Session = Depends(get_session)) -> None:
    """Delete a task."""
    task = _get_task_or_404(session, task_id)
    crud.delete_task(session, task)
