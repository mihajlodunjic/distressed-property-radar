from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_opportunity_alerts import AS_OF, create_listing, create_property, create_source

from app.api.dependencies import get_db_session
from app.core.config import Settings
from app.db.models import (
    Alert,
    JobRun,
    ListingEvent,
    ListingRawRecord,
    SourceRuntimeState,
)
from app.domain.enums import (
    AlertChannel,
    AlertStatus,
    AlertType,
    ListingEventType,
    ListingRawRecordType,
    SourceHealthStatus,
)
from app.main import create_app
from app.operations.backup import (
    BackupCommandError,
    create_database_backup,
    prune_backup_files,
    verify_database_restore,
)
from app.operations.maintenance import emit_source_health_alerts
from app.operations.recovery import prune_old_raw_records, recover_stale_running_jobs
from app.operations.status import build_operations_status


def test_stale_running_job_recovery_marks_failed_without_listing_changes(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase14_recovery")
    property_ = create_property(db_session)
    listing = create_listing(db_session, source, property_)
    state = SourceRuntimeState(
        source_id=source.id,
        last_attempt_at=AS_OF - timedelta(hours=4),
        last_success_at=AS_OF - timedelta(hours=5),
        health_status=SourceHealthStatus.HEALTHY,
    )
    db_session.add(state)
    stale_job = JobRun(
        job_type="four_zida_fast_discovery",
        source_id=source.id,
        started_at=AS_OF - timedelta(hours=3),
        status="RUNNING",
    )
    db_session.add(stale_job)
    db_session.flush()
    before_event_count = db_session.scalar(select(func.count()).select_from(ListingEvent))

    result = recover_stale_running_jobs(
        db_session,
        stale_after_seconds=3600,
        now=AS_OF,
        emit_alert=True,
    )
    second_result = recover_stale_running_jobs(
        db_session,
        stale_after_seconds=3600,
        now=AS_OF + timedelta(minutes=5),
        emit_alert=True,
    )

    assert result.recovered_count == 1
    assert result.recovered_job_ids == (stale_job.id,)
    assert second_result.recovered_count == 0
    assert stale_job.status == "FAILED"
    assert stale_job.finished_at == AS_OF
    assert "STALE_JOB_RECOVERY" in (stale_job.error_summary or "")
    assert listing.status.value == "ACTIVE"
    assert db_session.scalar(select(func.count()).select_from(ListingEvent)) == before_event_count
    assert (
        db_session.get(SourceRuntimeState, source.id).health_status == SourceHealthStatus.DEGRADED
    )
    operational_alerts = db_session.scalars(
        select(Alert).where(Alert.alert_type == AlertType.OPERATIONAL)
    ).all()
    assert len(operational_alerts) == 1


def test_recent_running_job_is_not_recovered(db_session: Session) -> None:
    source = create_source(db_session, "phase14_recent_job")
    job = JobRun(
        job_type="four_zida_fast_discovery",
        source_id=source.id,
        started_at=AS_OF - timedelta(minutes=5),
        status="RUNNING",
    )
    db_session.add(job)
    db_session.flush()

    result = recover_stale_running_jobs(
        db_session,
        stale_after_seconds=3600,
        now=AS_OF,
        emit_alert=True,
    )

    assert result.recovered_count == 0
    assert job.status == "RUNNING"
    assert db_session.scalar(select(func.count()).select_from(Alert)) == 0


def test_source_health_operational_alerts_are_deduped_by_cooldown(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase14_source_failure")
    db_session.add(
        SourceRuntimeState(
            source_id=source.id,
            last_attempt_at=AS_OF,
            last_success_at=AS_OF - timedelta(hours=12),
            last_error_at=AS_OF,
            last_error_type="HTTP_500",
            last_error_message="temporary source outage",
            recent_http_error_count=3,
            health_status=SourceHealthStatus.FAILED,
        )
    )
    db_session.flush()

    first = emit_source_health_alerts(
        db_session,
        settings=Settings(
            APP_ENV="test",
            SOURCE_STALE_AFTER_SECONDS=3600,
            OPERATIONAL_ALERT_COOLDOWN_SECONDS=3600,
        ),
        now=AS_OF,
    )
    second = emit_source_health_alerts(
        db_session,
        settings=Settings(
            APP_ENV="test",
            SOURCE_STALE_AFTER_SECONDS=3600,
            OPERATIONAL_ALERT_COOLDOWN_SECONDS=3600,
        ),
        now=AS_OF + timedelta(minutes=10),
    )

    failed_source_alerts = db_session.scalars(
        select(Alert).where(
            Alert.alert_type == AlertType.OPERATIONAL,
            Alert.reason_code == "SOURCE_FAILED",
        )
    ).all()
    assert "SOURCE_FAILED" in first.reason_codes
    assert "SOURCE_FAILED" in second.reason_codes
    assert len(failed_source_alerts) == 1
    assert source.code in failed_source_alerts[0].payload_json["message_text"]


def test_operations_status_reports_sources_jobs_analysis_alerts(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase14_status")
    db_session.add(
        SourceRuntimeState(
            source_id=source.id,
            last_attempt_at=AS_OF,
            last_success_at=AS_OF - timedelta(days=2),
            health_status=SourceHealthStatus.DEGRADED,
            last_error_message="parser degradation",
        )
    )
    db_session.add(
        JobRun(
            job_type="four_zida_fast_discovery",
            source_id=source.id,
            started_at=AS_OF - timedelta(minutes=20),
            finished_at=AS_OF - timedelta(minutes=19),
            status="FAILED",
        )
    )
    db_session.add(
        Alert(
            channel=AlertChannel.TELEGRAM,
            alert_type=AlertType.OPERATIONAL,
            priority=80,
            reason_code="SOURCE_FAILED",
            dedupe_key="operational:test:status",
            payload_json={"message_text": "Source failed."},
            status=AlertStatus.PENDING,
        )
    )
    db_session.flush()

    payload = build_operations_status(
        db_session,
        settings=Settings(APP_ENV="test", SOURCE_STALE_AFTER_SECONDS=3600),
        now=AS_OF,
    )

    assert payload["status"] == "ok"
    assert payload["scheduler"]["owner"] == "worker"
    assert payload["sources"]["summary"]["DEGRADED"] >= 1
    assert any(item["source_code"] == source.code for item in payload["sources"]["stale_sources"])
    assert payload["jobs"]["failed_last_24h"] >= 1
    assert payload["alerts"]["OPERATIONAL"]["PENDING"] >= 1
    assert payload["database"]["status"] == "ok"
    assert "free_bytes" in payload["disk"]


def test_private_operations_status_endpoint_uses_current_contract(
    db_session: Session,
) -> None:
    app = create_app()

    def override_db_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_db_session
    with TestClient(app) as client:
        response = client.get("/api/v1/operations/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["scheduler"]["api_runs_scheduler"] is False
    assert "readiness" in payload
    assert "sources" in payload


def test_backup_create_uses_pg_dump_without_secret_args_and_prunes_owned_files(
    tmp_path: Path,
) -> None:
    old_backup = tmp_path / "dpr-postgres-20200101T000000Z.dump"
    old_backup.write_bytes(b"old")
    unrelated_file = tmp_path / "manual-export.dump"
    unrelated_file.write_bytes(b"keep")
    old_timestamp = datetime(2020, 1, 1, tzinfo=UTC).timestamp()
    os.utime(old_backup, (old_timestamp, old_timestamp))
    commands: list[tuple[Sequence[str], Mapping[str, str], int]] = []

    def runner(
        command: Sequence[str],
        env: Mapping[str, str],
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[str]:
        commands.append((command, env, timeout_seconds))
        backup_path = Path(command[command.index("-f") + 1])
        backup_path.write_bytes(b"backup")
        return subprocess.CompletedProcess(list(command), 0, stdout="", stderr="")

    result = create_database_backup(
        database_url="postgresql+psycopg://user:secret@localhost:55432/dpr",
        output_dir=tmp_path,
        retention_days=14,
        now=datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
        runner=runner,
    )

    command, env, timeout_seconds = commands[0]
    assert result.size_bytes == len(b"backup")
    assert result.pruned_count == 1
    assert old_backup.exists() is False
    assert unrelated_file.exists() is True
    assert "secret" not in " ".join(command)
    assert env["PGPASSWORD"] == "secret"
    assert command[0] == "pg_dump"
    assert "-Fc" in command
    assert timeout_seconds == 3600


def test_backup_failure_raises_without_leaking_secret(tmp_path: Path) -> None:
    def runner(
        command: Sequence[str],
        env: Mapping[str, str],
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[str]:
        _ = env, timeout_seconds
        assert "secret" not in " ".join(command)
        return subprocess.CompletedProcess(list(command), 1, stdout="", stderr="pg_dump failed")

    try:
        create_database_backup(
            database_url="postgresql+psycopg://user:secret@localhost:55432/dpr",
            output_dir=tmp_path,
            runner=runner,
        )
    except BackupCommandError as exc:
        assert exc.operation == "pg_dump"
        assert exc.returncode == 1
    else:
        raise AssertionError("expected backup failure")


def test_restore_verification_runs_pg_restore_and_integrity_checks(tmp_path: Path) -> None:
    backup = tmp_path / "dpr-postgres-20260830T120000Z.dump"
    backup.write_bytes(b"backup")
    commands: list[Sequence[str]] = []

    def runner(
        command: Sequence[str],
        env: Mapping[str, str],
        timeout_seconds: int,
    ) -> subprocess.CompletedProcess[str]:
        _ = env, timeout_seconds
        commands.append(command)
        return subprocess.CompletedProcess(list(command), 0, stdout="", stderr="")

    result = verify_database_restore(
        database_url="postgresql+psycopg://user:secret@localhost:55432/dpr_restore",
        backup_path=backup,
        runner=runner,
    )

    encoded_commands = json.dumps([list(command) for command in commands])
    assert result.verified is True
    assert commands[0][0] == "pg_restore"
    assert "--clean" in commands[0]
    assert commands[1][0] == "psql"
    assert "postgis_version" in encoded_commands
    assert "secret" not in encoded_commands


def test_raw_record_retention_dry_run_and_apply_delete_only_raw_records(
    db_session: Session,
) -> None:
    source = create_source(db_session, "phase14_raw_retention")
    property_ = create_property(db_session)
    listing = create_listing(db_session, source, property_, asking_price=Decimal("125000.00"))
    event = ListingEvent(
        listing=listing,
        event_type=ListingEventType.PRICE_CHANGED,
        detected_at=AS_OF,
        old_price=Decimal("130000.00"),
        new_price=Decimal("125000.00"),
    )
    old_raw = ListingRawRecord(
        listing=listing,
        record_type=ListingRawRecordType.CARD,
        source_url=listing.url,
        raw_payload={"old": True},
        content_type="application/json",
        content_hash="phase14-old",
        captured_at=AS_OF - timedelta(days=120),
    )
    fresh_raw = ListingRawRecord(
        listing=listing,
        record_type=ListingRawRecordType.CARD,
        source_url=listing.url,
        raw_payload={"fresh": True},
        content_type="application/json",
        content_hash="phase14-fresh",
        captured_at=AS_OF - timedelta(days=2),
    )
    db_session.add_all([event, old_raw, fresh_raw])
    db_session.flush()

    dry_run = prune_old_raw_records(
        db_session,
        retention_days=90,
        now=AS_OF,
        dry_run=True,
    )
    applied = prune_old_raw_records(
        db_session,
        retention_days=90,
        now=AS_OF,
        dry_run=False,
    )

    assert dry_run.matched_count == 1
    assert dry_run.deleted_count == 0
    assert applied.deleted_count == 1
    assert db_session.get(ListingRawRecord, fresh_raw.id) is not None
    assert db_session.get(ListingEvent, event.id) is not None
    assert db_session.get(ListingRawRecord, old_raw.id) is None


def test_backup_retention_prune_dry_run_keeps_files(tmp_path: Path) -> None:
    backup = tmp_path / "dpr-postgres-20200101T000000Z.dump"
    backup.write_bytes(b"old")
    old_timestamp = datetime(2020, 1, 1, tzinfo=UTC).timestamp()
    os.utime(backup, (old_timestamp, old_timestamp))

    result = prune_backup_files(
        tmp_path,
        retention_days=14,
        now=datetime(2026, 8, 30, tzinfo=UTC),
        dry_run=True,
    )

    assert result.matched_count == 1
    assert result.deleted_count == 0
    assert backup.exists() is True
