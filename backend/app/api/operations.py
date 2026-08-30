from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session, require_api_access
from app.operations.status import build_operations_status

router = APIRouter(prefix="/api/v1/operations", dependencies=[Depends(require_api_access)])

DbSession = Annotated[Session, Depends(get_db_session)]


@router.get("/status")
def get_operations_status(session: DbSession) -> dict[str, Any]:
    return build_operations_status(session)
