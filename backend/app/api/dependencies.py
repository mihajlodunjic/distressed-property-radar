from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal


def get_db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def require_api_access(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    settings = get_settings()
    expected_token = settings.api_access_token

    if not expected_token:
        if settings.app_env.lower() in {"production", "prod"}:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="API access token is not configured.",
            )
        return

    if authorization != f"Bearer {expected_token}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
