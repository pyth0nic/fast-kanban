"""HTTP routes exposing the kanban task API."""
import hashlib
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlmodel import Session, select

from app import crud
from app.database import get_session
from app.models import (
    TaskCreate,
    TaskEvent,
    TaskIdempotencyRecord,
    TaskOutboxEventRead,
    TaskPriority,
    TaskRead,
    TaskStatus,
    TaskUpdate,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _get_task_or_404(session: Session, task_id: int):
    task = crud.get_task(session, task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


def _task_idempotency_scope(payload: TaskCreate | TaskUpdate, workspace_id: Optional[str]) -> str:
    if workspace_id:
        return workspace_id
    if isinstance(payload, TaskCreate):
        return payload.workspace_id or "global"
    return "global"


def _request_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _read_idempotency_record(session: Session, key: str, scope: str) -> Optional[TaskIdempotencyRecord]:
    return session.exec(
        select(TaskIdempotencyRecord).where(
            TaskIdempotencyRecord.scope == scope,
            TaskIdempotencyRecord.key == key,
        )
    ).first()


def _mutation_response(
    session: Session,
    *,
    key: Optional[str],
    scope: str,
    payload: object,
    status_code: int,
    response_data: object,
) -> object:
    if key is None:
        return response_data
    request_hash = _request_hash(payload)
    record = _read_idempotency_record(session, key, scope)
    if record is not None:
        if record.request_hash != request_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key already used for a different request body.",
            )
        return json.loads(record.response_body)
    body = json.dumps(response_data, sort_keys=True, default=str)
    session.add(
        TaskIdempotencyRecord(
            scope=scope,
            key=key,
            request_hash=request_hash,
            response_status=status_code,
            response_body=body,
        )
    )
    session.commit()
    return response_data


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    session: Session = Depends(get_session),
    response: Response = None,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    workspace_scope: Optional[str] = Header(default=None, alias="X-Workspace-Id"),
) -> TaskRead:
    """Create a new kanban task."""
    scope = _task_idempotency_scope(payload, workspace_scope)
    if idempotency_key is not None:
        existing = _read_idempotency_record(session, idempotency_key, scope)
        if existing is not None:
            if existing.request_hash != _request_hash(payload.model_dump(mode="json")):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key already used for a different request body.",
                )
            task = TaskRead.model_validate(json.loads(existing.response_body))
            response.headers["ETag"] = crud.task_etag(task)
            return task

    task = crud.create_task(session, payload)
    task_read = TaskRead.model_validate(task)
    if idempotency_key is not None:
        _mutation_response(
            session,
            key=idempotency_key,
            scope=scope,
            payload=payload.model_dump(mode="json"),
            status_code=status.HTTP_201_CREATED,
            response_data=task_read.model_dump(mode="json"),
        )
    response.headers["ETag"] = crud.task_etag(task_read)
    return task_read


@router.get("", response_model=list[TaskRead])
def list_tasks(
    status_filter: Optional[TaskStatus] = None,
    status: Optional[TaskStatus] = None,
    workspace_id: Optional[str] = None,
    assignee_id: Optional[str] = None,
    priority: Optional[str] = None,
    labels: Optional[list[str]] = Query(default=None),
    due_after: Optional[str] = None,
    due_before: Optional[str] = None,
    limit: Optional[int] = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[TaskRead]:
    """List tasks, optionally filtered by metadata and date windows."""
    resolved_status = status_filter if status is None else status
    due_after_dt = None if due_after is None else datetime.fromisoformat(due_after)
    due_before_dt = None if due_before is None else datetime.fromisoformat(due_before)
    return list(
        crud.list_tasks(
            session,
            status=resolved_status,
            workspace_id=workspace_id,
            assignee_id=assignee_id,
            priority=None if priority is None else TaskPriority(priority),
            labels=labels,
            due_after=due_after_dt,
            due_before=due_before_dt,
            limit=limit,
            offset=offset,
        )
    )


@router.get("/outbox", response_model=list[TaskOutboxEventRead])
def outbox_events(
    cursor: int = Query(default=0, ge=0),
    limit: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_session),
) -> list[TaskOutboxEventRead]:
    """Poll the transactional task outbox using a cursor for reliable replay."""
    return list(crud.list_outbox_events(session, cursor=cursor, limit=limit))


@router.get("/{task_id}", response_model=TaskRead)
def get_task(
    task_id: int,
    session: Session = Depends(get_session),
    response: Response = None,
) -> TaskRead:
    """Fetch a single task by id."""
    task = _get_task_or_404(session, task_id)
    response.headers["ETag"] = crud.task_etag(task)
    return task


@router.patch("/{task_id}", response_model=TaskRead)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    session: Session = Depends(get_session),
    response: Response = None,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    workspace_scope: Optional[str] = Header(default=None, alias="X-Workspace-Id"),
) -> TaskRead:
    """Partially update a task's title, description, or status."""
    task = _get_task_or_404(session, task_id)
    if not crud.matches_etag(task, if_match):
        raise HTTPException(status_code=status.HTTP_412_PRECONDITION_FAILED, detail="ETag mismatch")
    scope = _task_idempotency_scope(payload, workspace_scope) or task.workspace_id or "global"
    if idempotency_key is not None:
        existing = _read_idempotency_record(session, idempotency_key, scope)
        if existing is not None:
            if existing.request_hash != _request_hash(payload.model_dump(mode="json")):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key already used for a different request body.",
                )
            updated = TaskRead.model_validate(json.loads(existing.response_body))
            response.headers["ETag"] = crud.task_etag(updated)
            return updated

    updated = crud.update_task(session, task, payload)
    updated_read = TaskRead.model_validate(updated)
    if idempotency_key is not None:
        _mutation_response(
            session,
            key=idempotency_key,
            scope=scope,
            payload=payload.model_dump(mode="json"),
            status_code=status.HTTP_200_OK,
            response_data=updated_read.model_dump(mode="json"),
        )
    response.headers["ETag"] = crud.task_etag(updated_read)
    return updated_read


@router.post("/{task_id}/progress", response_model=TaskRead)
def progress_task(
    task_id: int,
    session: Session = Depends(get_session),
    response: Response = None,
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
) -> TaskRead:
    """Advance a task to the next kanban column (backlog -> todo -> in_progress -> done)."""
    task = _get_task_or_404(session, task_id)
    if not crud.matches_etag(task, if_match):
        raise HTTPException(status_code=status.HTTP_412_PRECONDITION_FAILED, detail="ETag mismatch")
    updated = crud.progress_task(session, task)
    response.headers["ETag"] = crud.task_etag(updated)
    return updated


@router.get("/{task_id}/events", response_model=list[TaskEvent])
def task_events(task_id: int, session: Session = Depends(get_session)) -> list[TaskEvent]:
    """Return the versioned lifecycle event stream for a task."""
    _get_task_or_404(session, task_id)
    return list(crud.get_task_events(session, task_id))


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    session: Session = Depends(get_session),
    if_match: Optional[str] = Header(default=None, alias="If-Match"),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    workspace_scope: Optional[str] = Header(default=None, alias="X-Workspace-Id"),
) -> None:
    """Delete a task."""
    task = _get_task_or_404(session, task_id)
    if not crud.matches_etag(task, if_match):
        raise HTTPException(status_code=status.HTTP_412_PRECONDITION_FAILED, detail="ETag mismatch")
    scope = workspace_scope or task.workspace_id or "global"
    if idempotency_key is not None:
        request_payload = {"method": "DELETE", "task_id": task_id}
        existing = _read_idempotency_record(session, idempotency_key, scope)
        if existing is not None:
            if existing.request_hash != _request_hash(request_payload):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key already used for a different request body.",
                )
            return
    crud.delete_task(session, task)
    if idempotency_key is not None:
        _mutation_response(
            session,
            key=idempotency_key,
            scope=scope,
            payload={"method": "DELETE", "task_id": task_id},
            status_code=status.HTTP_204_NO_CONTENT,
            response_data={},
        )
