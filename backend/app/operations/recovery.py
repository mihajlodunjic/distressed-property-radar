from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import JobRun, ListingRawRecord, SourceRuntimeState
from app.domain.enums import SourceHealthStatus
from app.operations.alerts import create_deduped_operational_alert

STALE_JOB_ERROR_TYPE = "STALE_JOB_RECOVERY"


@dataclass(frozen=True)
class StaleJobRecoveryResult:
    recovered_count: int
    recovered_job_ids: tuple[UUID, ...]

    def to_jsonable(self) -> dict[str, object]:
        return {
            "recovered_count": self.recovered_count,
            "recovered_job_ids": [str(job_id) for job_id in self.recovered_job_ids],
        }


@dataclass(frozen=True)
class RawRecordRetentionResult:
    cutoff_at: datetime
    matched_count: int
    deleted_count: int
    dry_run: bool

    def to_jsonable(self) -> dict[str, object]:
        return {
            "cutoff_at": self.cutoff_at.isoformat(),
            "matched_count": self.matched_count,
            "deleted_count": self.deleted_count,
            "dry_run": self.dry_run,
        }


def recover_stale_running_jobs(
    session: Session,
    *,
    stale_after_seconds: int,
    now: datetime | None = None,
    emit_alert: bool = False,
    alert_cooldown_seconds: int = 21_600,
    commit: bool = False,
) -> StaleJobRecoveryResult:
    observed_at = _aware_datetime(now or datetime.now(UTC))
    cutoff = observed_at - timedelta(seconds=stale_after_seconds)
    jobs = session.scalars(
        select(JobRun)
        .where(JobRun.status == "RUNNING", JobRun.started_at < cutoff)
        .order_by(JobRun.started_at.asc(), JobRun.id.asc())
    ).all()

    recovered_ids: list[UUID] = []
    for job in jobs:
        job.status = "FAILED"
        job.finished_at = observed_at
        job.error_summary = _recovery_error_summary(job)
        recovered_ids.append(job.id)
        _mark_source_degraded(session, job, observed_at)

    if recovered_ids and emit_alert:
        create_deduped_operational_alert(
            session,
            reason_code=STALE_JOB_ERROR_TYPE,
            subject_key="running_jobs",
            message_text=(
                f"Recovered {len(recovered_ids)} stale RUNNING job(s). "
                "They were marked FAILED for normal retry/idempotent recovery."
            ),
            priority=80,
            cooldown_seconds=alert_cooldown_seconds,
            now=observed_at,
        )

    session.flush()
    if commit:
        session.commit()
    return StaleJobRecoveryResult(
        recovered_count=len(recovered_ids),
        recovered_job_ids=tuple(recovered_ids),
    )


def prune_old_raw_records(
    session: Session,
    *,
    retention_days: int,
    now: datetime | None = None,
    dry_run: bool = True,
    commit: bool = False,
) -> RawRecordRetentionResult:
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")

    observed_at = _aware_datetime(now or datetime.now(UTC))
    cutoff = observed_at - timedelta(days=retention_days)
    records = session.scalars(
        select(ListingRawRecord)
        .where(ListingRawRecord.captured_at < cutoff)
        .order_by(ListingRawRecord.captured_at.asc(), ListingRawRecord.id.asc())
    ).all()

    deleted_count = 0
    if not dry_run:
        for record in records:
            session.delete(record)
            deleted_count += 1
        session.flush()
        if commit:
            session.commit()

    return RawRecordRetentionResult(
        cutoff_at=cutoff,
        matched_count=len(records),
        deleted_count=deleted_count,
        dry_run=dry_run,
    )


def _mark_source_degraded(session: Session, job: JobRun, observed_at: datetime) -> None:
    if job.source_id is None:
        return
    state = session.get(SourceRuntimeState, job.source_id)
    if state is None:
        return
    state.health_status = SourceHealthStatus.DEGRADED
    state.last_error_at = observed_at
    state.last_error_type = STALE_JOB_ERROR_TYPE
    state.last_error_message = (
        f"Job {job.id} was left RUNNING after worker interruption and was marked FAILED."
    )


def _recovery_error_summary(job: JobRun) -> str:
    message = (
        f"{STALE_JOB_ERROR_TYPE}: job left RUNNING after worker interruption; "
        "marked FAILED for idempotent retry."
    )
    if job.error_summary:
        if STALE_JOB_ERROR_TYPE in job.error_summary:
            return job.error_summary
        return f"{job.error_summary}\n{message}"[:4000]
    return message


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
