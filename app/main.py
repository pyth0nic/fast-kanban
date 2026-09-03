"""FastAPI application entrypoint for Fast Kanban."""
from fastapi import FastAPI

from app.config import get_settings
from app.routers.tasks import router as tasks_router

settings = get_settings()

# The database schema is managed exclusively by Alembic migrations
# (see alembic/ and README.MD) rather than being created at app startup.
app = FastAPI(title=settings.app_name)
app.include_router(tasks_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    """Simple liveness probe."""
    return {"status": "ok"}
