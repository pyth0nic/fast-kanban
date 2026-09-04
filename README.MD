# Fast Kanban

A lightweight [FastAPI](https://fastapi.tiangolo.com/) application that exposes a kanban board
over a REST API, backed by SQLite. Tasks flow through the columns
`backlog -> todo -> in_progress -> done`.

## Design

- **Pydantic / SQLModel** models the domain (`app/models.py`): `Task`, `TaskStatus`,
  and request/response schemas (`TaskCreate`, `TaskUpdate`, `TaskRead`).
- **python-dotenv** (via `pydantic-settings`) loads configuration from a `.env` file
  (`app/config.py`).
- **Functional core, imperative shell**: pure business-rule functions (e.g. `next_status`,
  `compute_changes` in `app/crud.py`) are kept separate from the thin, side-effecting
  database calls that use them.
- **Alembic** manages the SQLite schema as versioned migrations (`alembic/`), instead of
  relying on ad-hoc `create_all()` calls at runtime.
- SQLite connections use **WAL (Write-Ahead Logging)** journal mode (`app/database.py`) for
  better read/write concurrency than the default rollback journal.

## Project layout

```
app/
  main.py        FastAPI app + routing setup
  config.py       dotenv-backed settings
  database.py     SQLModel engine/session
  models.py       Pydantic/SQLModel domain models
  crud.py         Functional business logic + persistence
  routers/tasks.py  Task API endpoints
alembic/          Database migrations
tests/            Pytest test suite
```

## Getting started

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # customize as needed

# Apply database migrations
alembic upgrade head

# Run the API
uvicorn app.main:app --reload
```

The API is served at http://127.0.0.1:8000, with interactive docs at `/docs`.

## Docker

Build and run the containerized app (migrations run automatically on start):

```bash
docker build -t fast-kanban .
docker run -p 8000:8000 -v fast-kanban-data:/data fast-kanban
```

The SQLite database is stored in the `/data` volume so it persists across container restarts.
Override `DATABASE_URL` (and other settings from `.env.example`) with `-e` flags as needed.

## API

| Method | Path                    | Description                                                  |
|--------|-------------------------|---------------------------------------------------------------|
| POST   | `/tasks`                | Create a task                                                 |
| GET    | `/tasks`                | List tasks with optional filters (`workspace_id`, `assignee_id`, `status_filter`, `labels`, `due_after`, `due_before`, `limit`, `offset`) |
| GET    | `/tasks/{id}`           | Get a task                                                    |
| PATCH  | `/tasks/{id}`           | Update a task's fields, guarded by `If-Match` / ETag          |
| POST   | `/tasks/{id}/progress`  | Advance a task to the next kanban column                      |
| GET    | `/tasks/{id}/events`    | Fetch the task's versioned lifecycle events                   |
| GET    | `/tasks/outbox`         | Poll lifecycle events from the transactional outbox           |
| DELETE | `/tasks/{id}`           | Delete a task                                                 |
| GET    | `/health`               | Liveness probe                                                |

The stable task payload includes `workspace_id`, `assignee_id`, `priority`, `due_at`, `labels`, `external_ref`, and a monotonically increasing `version`. Each response includes an `ETag` value (`W/"<version>"`) so stale writes can be rejected with `If-Match` headers. Requests that mutate state may include `Idempotency-Key` and `X-Workspace-Id` headers; identical payloads replay the previous response and conflicting redispatches return `409 Conflict`.

## API contract and compatibility

- The task schema is versioned in the API contract and should only be evolved with additive fields or backward-compatible defaults.
- Existing clients may rely on the default values for newly introduced fields (`priority=medium`, `labels=[]`, `workspace_id=""`, `assignee_id=null`).
- Breaking changes require a documented migration path and a new contract version, while the legacy route and payload remain available for the deprecation window.
- Outbox payloads are intentionally transport-neutral: consumers may bridge them to Redis, Kafka, or an in-process queue without changing the stored event format.

## Migrations

Whenever `app/models.py` changes, generate a new migration and review it before committing:

```bash
alembic revision --autogenerate -m "describe the change"
```

> Note: Alembic's autogenerate does not always add the `import sqlmodel` statement needed
> for SQLModel column types—double-check the generated file's imports before applying it.

## Tests

```bash
pytest
```

