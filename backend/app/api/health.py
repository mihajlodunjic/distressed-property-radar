from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.db.session import database_is_reachable, get_postgis_version

router = APIRouter()


@router.get("/health")
def health() -> JSONResponse:
    settings = get_settings()
    database_ok = database_is_reachable()
    postgis_version = get_postgis_version()
    postgis_ok = postgis_version is not None
    healthy = database_ok and postgis_ok

    return JSONResponse(
        status_code=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "status": "ok" if healthy else "degraded",
            "environment": settings.app_env,
            "database": {"status": "ok" if database_ok else "error"},
            "postgis": {
                "status": "ok" if postgis_ok else "error",
                "version": postgis_version,
            },
        },
    )
