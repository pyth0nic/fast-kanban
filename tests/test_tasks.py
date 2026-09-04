"""Tests for the kanban task API."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

TEST_DB_PATH = Path(__file__).parent / "test_kanban.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"

from app.database import get_session  # noqa: E402
from app.main import app  # noqa: E402

engine = create_engine(f"sqlite:///{TEST_DB_PATH}", connect_args={"check_same_thread": False})


@pytest.fixture(autouse=True)
def _fresh_database():
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


def _override_get_session():
    with Session(engine) as session:
        yield session


app.dependency_overrides[get_session] = _override_get_session
client = TestClient(app)


def test_create_task_defaults_to_backlog():
    response = client.post("/tasks", json={"title": "Write docs"})
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Write docs"
    assert body["status"] == "backlog"


def test_list_tasks_filters_by_status():
    client.post("/tasks", json={"title": "A", "status": "todo"})
    client.post("/tasks", json={"title": "B", "status": "done"})

    response = client.get("/tasks", params={"status_filter": "todo"})
    assert response.status_code == 200
    titles = [t["title"] for t in response.json()]
    assert titles == ["A"]


def test_progress_task_moves_through_columns():
    created = client.post("/tasks", json={"title": "Ship it"}).json()
    task_id = created["id"]
    assert created["status"] == "backlog"

    for expected in ("todo", "in_progress", "done"):
        response = client.post(f"/tasks/{task_id}/progress")
        assert response.status_code == 200
        assert response.json()["status"] == expected

    # Progressing a done task keeps it done.
    response = client.post(f"/tasks/{task_id}/progress")
    assert response.json()["status"] == "done"


def test_update_task_partial_fields():
    created = client.post("/tasks", json={"title": "Old title"}).json()
    task_id = created["id"]

    response = client.patch(f"/tasks/{task_id}", json={"description": "New description"})
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Old title"
    assert body["description"] == "New description"


def test_task_metadata_filters_and_idempotency_work():
    task_due = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0)
    create = client.post(
        "/tasks",
        json={
            "title": "Priority card",
            "workspace_id": "workspace-a",
            "assignee_id": "user-42",
            "priority": "high",
            "due_at": task_due.isoformat(),
            "labels": ["ops", "urgent"],
            "external_ref": "EXT-42",
        },
        headers={"Idempotency-Key": "alpha", "X-Workspace-Id": "workspace-a"},
    )
    assert create.status_code == 201
    body = create.json()
    assert body["priority"] == "high"
    assert body["version"] == 1
    assert body["workspace_id"] == "workspace-a"

    filtered = client.get(
        "/tasks",
        params={"workspace_id": "workspace-a", "assignee_id": "user-42", "labels": ["ops"], "limit": 10},
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1

    etag = create.headers["ETag"]
    stale = client.patch(
        f"/tasks/{body['id']}",
        json={"title": "Updated title"},
        headers={"If-Match": 'W/"999"'},
    )
    assert stale.status_code == 412

    updated = client.patch(
        f"/tasks/{body['id']}",
        json={"title": "Updated title"},
        headers={"If-Match": etag, "Idempotency-Key": "beta", "X-Workspace-Id": "workspace-a"},
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated title"
    assert updated.json()["version"] == 2

    replay = client.patch(
        f"/tasks/{body['id']}",
        json={"title": "Updated title"},
        headers={"If-Match": updated.headers["ETag"], "Idempotency-Key": "beta", "X-Workspace-Id": "workspace-a"},
    )
    assert replay.status_code == 200
    assert replay.json()["version"] == 2

    events = client.get(f"/tasks/{body['id']}/events")
    assert events.status_code == 200
    assert len(events.json()) >= 2

    outbox = client.get("/tasks/outbox", params={"limit": 10})
    assert outbox.status_code == 200
    assert len(outbox.json()) >= 1


def test_get_and_delete_missing_task_returns_404():
    assert client.get("/tasks/999").status_code == 404
    assert client.delete("/tasks/999").status_code == 404


def test_delete_task():
    created = client.post("/tasks", json={"title": "Temporary"}).json()
    task_id = created["id"]

    response = client.delete(f"/tasks/{task_id}")
    assert response.status_code == 204
    assert client.get(f"/tasks/{task_id}").status_code == 404
