from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.api.operations import router as operations_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.observability import RequestLoggingMiddleware
from app.db.session import database_is_reachable

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(
        settings.log_level,
        log_format=settings.log_format,
        log_file=settings.log_file,
        log_max_bytes=settings.log_max_bytes,
        log_backup_count=settings.log_backup_count,
    )
    logger.info(
        "backend startup environment=%s app_version=%s process_type=api database_reachable=%s",
        settings.app_env,
        settings.app_version,
        database_is_reachable(),
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Distressed Property Radar", lifespan=lifespan)
    app.add_middleware(RequestLoggingMiddleware)
    allowed_origins = [
        origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()
    ]
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )
    app.include_router(health_router)
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(dashboard_router)
    app.include_router(operations_router)
    return app


app = create_app()
