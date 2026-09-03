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

## API

| Method | Path                    | Description                              |
|--------|-------------------------|-------------------------------------------|
| POST   | `/tasks`                | Create a task                             |
| GET    | `/tasks`                | List tasks (optional `status_filter`)     |
| GET    | `/tasks/{id}`           | Get a task                                |
| PATCH  | `/tasks/{id}`           | Update a task's title/description/status  |
| POST   | `/tasks/{id}/progress`  | Advance a task to the next kanban column  |
| DELETE | `/tasks/{id}`           | Delete a task                             |
| GET    | `/health`               | Liveness probe                            |

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

