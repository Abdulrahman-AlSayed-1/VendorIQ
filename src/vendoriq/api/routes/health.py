from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from vendoriq.api.deps import SessionDep
from vendoriq.core.config import settings
from vendoriq.schemas.health import HealthCheckResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthCheckResponse)
async def health_check(session: SessionDep) -> HealthCheckResponse:
    db_status = "connected"
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db_status = "unavailable"

    overall_status = "healthy" if db_status == "connected" else "degraded"
    return HealthCheckResponse(
        status=overall_status,
        project=settings.PROJECT_NAME,
        version=settings.VERSION,
        database=db_status,
    )
