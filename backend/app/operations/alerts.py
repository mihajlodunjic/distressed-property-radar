from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Alert
from app.domain.enums import AlertType
from app.opportunities.opportunity_engine import create_operational_telegram_alert


def create_deduped_operational_alert(
    session: Session,
    *,
    reason_code: str,
    subject_key: str,
    message_text: str,
    priority: int = 50,
    cooldown_seconds: int = 21_600,
    now: datetime | None = None,
) -> Alert:
    observed_at = _aware_datetime(now or datetime.now(UTC))
    normalized_reason = _dedupe_component(reason_code)
    normalized_subject = _dedupe_component(subject_key)
    prefix = f"operational:{normalized_reason}:{normalized_subject}:"

    if cooldown_seconds > 0:
        cutoff = observed_at - timedelta(seconds=cooldown_seconds)
        existing = session.scalars(
            select(Alert)
            .where(
                Alert.alert_type == AlertType.OPERATIONAL,
                Alert.reason_code == reason_code,
                Alert.dedupe_key.like(f"{prefix}%"),
                Alert.created_at >= cutoff,
            )
            .order_by(Alert.created_at.desc(), Alert.id.desc())
        ).first()
        if existing is not None:
            return existing

    dedupe_key = f"{prefix}{observed_at.strftime('%Y%m%dT%H%M%SZ')}"
    return create_operational_telegram_alert(
        session,
        reason_code=reason_code,
        message_text=message_text,
        dedupe_key=dedupe_key,
        priority=priority,
    )


def _dedupe_component(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value.strip().lower()).strip("_")
    return normalized or "unknown"


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
