from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import Source, SourceRuntimeState
from app.domain.enums import SourceHealthStatus
from app.operations.alerts import create_deduped_operational_alert
from app.operations.recovery import (
    RawRecordRetentionResult,
    StaleJobRecoveryResult,
    prune_old_raw_records,
    recover_stale_running_jobs,
)


@dataclass(frozen=True)
class SourceAlertResult:
    created_or_existing_count: int
    reason_codes: tuple[str, ...]

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "created_or_existing_count": self.created_or_existing_count,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class MaintenanceResult:
    recovered_jobs: StaleJobRecoveryResult
    source_alerts: SourceAlertResult
    raw_retention: RawRecordRetentionResult

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "recovered_jobs": self.recovered_jobs.to_jsonable(),
            "source_alerts": self.source_alerts.to_jsonable(),
            "raw_retention": self.raw_retention.to_jsonable(),
        }


def run_operational_maintenance(
    session: Session,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
    apply_raw_retention: bool = False,
    commit: bool = False,
) -> MaintenanceResult:
    effective_settings = settings or get_settings()
    observed_at = _aware_datetime(now or datetime.now(UTC))
    recovered_jobs = recover_stale_running_jobs(
        session,
        stale_after_seconds=effective_settings.stale_job_timeout_seconds,
        now=observed_at,
        emit_alert=True,
        alert_cooldown_seconds=effective_settings.operational_alert_cooldown_seconds,
    )
    source_alerts = emit_source_health_alerts(
        session,
        settings=effective_settings,
        now=observed_at,
    )
    raw_retention = prune_old_raw_records(
        session,
        retention_days=effective_settings.raw_record_retention_days,
        now=observed_at,
        dry_run=not apply_raw_retention,
    )
    if commit:
        session.commit()
    return MaintenanceResult(
        recovered_jobs=recovered_jobs,
        source_alerts=source_alerts,
        raw_retention=raw_retention,
    )


def emit_source_health_alerts(
    session: Session,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> SourceAlertResult:
    effective_settings = settings or get_settings()
    observed_at = _aware_datetime(now or datetime.now(UTC))
    stale_cutoff = observed_at - timedelta(seconds=effective_settings.source_stale_after_seconds)
    rows = session.execute(
        select(Source, SourceRuntimeState).outerjoin(
            SourceRuntimeState,
            SourceRuntimeState.source_id == Source.id,
        )
    ).all()

    reason_codes: list[str] = []
    created_or_existing_count = 0
    for source, state in rows:
        if not source.is_enabled:
            continue
        if not (
            source.supports_discovery or source.supports_market_scan or source.supports_detail_fetch
        ):
            continue
        reason_code: str | None = None
        message: str | None = None
        priority = 50
        if state is None:
            reason_code = "SOURCE_HEALTH_UNKNOWN"
            message = f"Source {source.code} has no runtime health state."
            priority = 70
        elif state.health_status == SourceHealthStatus.FAILED:
            reason_code = "SOURCE_FAILED"
            message = f"Source {source.code} is FAILED: {state.last_error_message or 'no details'}"
            priority = 80
        elif state.health_status == SourceHealthStatus.DEGRADED:
            reason_code = "SOURCE_DEGRADED"
            message = (
                f"Source {source.code} is DEGRADED: {state.last_error_message or 'no details'}"
            )
            priority = 60
        elif state.last_success_at is None or _aware_datetime(state.last_success_at) < stale_cutoff:
            reason_code = "SOURCE_STALE"
            message = f"Source {source.code} has not had a successful crawl recently."
            priority = 60

        if reason_code is None or message is None:
            continue
        create_deduped_operational_alert(
            session,
            reason_code=reason_code,
            subject_key=source.code,
            message_text=message,
            priority=priority,
            cooldown_seconds=effective_settings.operational_alert_cooldown_seconds,
            now=observed_at,
        )
        reason_codes.append(reason_code)
        created_or_existing_count += 1

    session.flush()
    return SourceAlertResult(
        created_or_existing_count=created_or_existing_count,
        reason_codes=tuple(reason_codes),
    )


def create_backup_failure_alert(
    session: Session,
    *,
    message_text: str,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> None:
    effective_settings = settings or get_settings()
    create_deduped_operational_alert(
        session,
        reason_code="BACKUP_FAILED",
        subject_key="database",
        message_text=message_text,
        priority=90,
        cooldown_seconds=effective_settings.operational_alert_cooldown_seconds,
        now=now,
    )
    session.flush()


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
