import logging
from typing import Literal

from alembic.runtime.migration import MigrationContext
from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import DatabaseSession

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])
# Update alongside migrations; readiness requires the deployed schema revision.
SCHEMA_REVISION = "0002_agent_management"


class HealthResponse(BaseModel):
    status: Literal["ok", "error"]
    service: str = "bia-api"
    database: Literal["ok", "error"] | None = None
    migrations: Literal["ok", "pending", "unknown"] | None = None


@router.get("/health", response_model=HealthResponse, response_model_exclude_none=True)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=HealthResponse)
def readiness(response: Response, session: DatabaseSession) -> HealthResponse:
    try:
        session.execute(text("SELECT 1"))
        heads = MigrationContext.configure(session.connection()).get_current_heads()
    except SQLAlchemyError:
        # Do not return connection details or credentials in errors/log messages.
        logger.warning("Database readiness check failed")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="error", database="error", migrations="unknown")
    if heads != (SCHEMA_REVISION,):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(status="error", database="ok", migrations="pending")
    return HealthResponse(status="ok", database="ok", migrations="ok")
