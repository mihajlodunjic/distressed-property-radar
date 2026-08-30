from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import func, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import Alert, JobRun, PropertyAnalysisState, Source, SourceRuntimeState
from app.db.session import SessionLocal, get_engine
from app.domain.enums import AlertStatus, AlertType, AnalysisStatus, SourceHealthStatus

BACKEND_ROOT = Path(__file__).resolve().parents[2]
BACKUP_FILE_PATTERN = "dpr-postgres-*.dump"


def build_readiness_report(
    *,
    settings: Settings | None = None,
    engine: Engine | None = None,
) -> dict[str, Any]:
    effective_settings = settings or get_settings()
    database = _database_readiness(engine or get_engine())
    configuration = _configuration_readiness(effective_settings)
    ready = (
        database["status"] == "ok"
        and database["postgis"]["status"] == "ok"
        and database["migrations"]["status"] == "ok"
        and configuration["status"] == "ok"
    )
    return {
        "status": "ready" if ready else "not_ready",
        "ready": ready,
        "environment": effective_settings.app_env,
        "release": {"app_version": effective_settings.app_version},
        "database": {
            "status": database["status"],
            "error": database.get("error"),
        },
        "postgis": database["postgis"],
        "migrations": database["migrations"],
        "configuration": configuration,
    }


def build_operations_status(
    session: Session,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    effective_settings = settings or get_settings()
    observed_at = _aware_datetime(now or datetime.now(UTC))
    readiness = build_readiness_report(settings=effective_settings)
    return {
        "status": "ok" if readiness["ready"] else "degraded",
        "observed_at": observed_at.isoformat(),
        "release": readiness["release"],
        "scheduler": _scheduler_status(effective_settings),
        "database": _database_metrics(session),
        "disk": _disk_status(effective_settings),
        "backup": _backup_status(effective_settings, observed_at),
        "sources": _source_status(session, effective_settings, observed_at),
        "jobs": _job_status(session, effective_settings, observed_at),
        "analysis": _analysis_status(session),
        "alerts": _alert_status(session),
        "readiness": readiness,
    }


def _database_readiness(engine: Engine) -> dict[str, Any]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            postgis_version = connection.execute(text("SELECT postgis_version()")).scalar_one()
            migration_context = MigrationContext.configure(connection)
            current_heads = set(migration_context.get_current_heads())

        config = _alembic_config()
        expected_heads = set(ScriptDirectory.from_config(config).get_heads())
        migrations_ok = current_heads == expected_heads
        return {
            "status": "ok",
            "postgis": {
                "status": "ok",
                "version": postgis_version,
            },
            "migrations": {
                "status": "ok" if migrations_ok else "error",
                "current_heads": sorted(current_heads),
                "expected_heads": sorted(expected_heads),
            },
        }
    except SQLAlchemyError as exc:
        return _database_error_report(exc)
    except Exception as exc:
        return _database_error_report(exc)


def _database_error_report(exc: Exception) -> dict[str, Any]:
    return {
        "status": "error",
        "error": type(exc).__name__,
        "postgis": {"status": "unknown", "version": None},
        "migrations": {
            "status": "unknown",
            "current_heads": [],
            "expected_heads": [],
        },
    }


def _configuration_readiness(settings: Settings) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    production = settings.app_env.lower() in {"production", "prod"}
    origins = _cors_origins(settings)

    if production and not settings.api_access_token:
        errors.append("API_ACCESS_TOKEN is required in production.")
    if "*" in origins:
        errors.append("Wildcard CORS origin is not allowed.")
    if production and settings.app_base_url.startswith("http://"):
        warnings.append("APP_BASE_URL should be the HTTPS/private production URL.")
    if production and not settings.backup_offserver_configured:
        warnings.append("Off-server backup destination is not marked as configured.")

    return {
        "status": "ok" if not errors else "error",
        "errors": errors,
        "warnings": warnings,
        "production": production,
        "cors_allowed_origins_count": len(origins),
        "api_access_configured": bool(settings.api_access_token),
        "telegram_configured": bool(settings.telegram_bot_token and settings.telegram_chat_id),
        "llm_configured": bool(settings.llm_api_key),
        "backup_offserver_configured": settings.backup_offserver_configured,
    }


def _scheduler_status(settings: Settings) -> dict[str, Any]:
    owner = settings.scheduler_owner.strip() or "worker"
    return {
        "owner": owner,
        "api_runs_scheduler": False,
        "single_owner_required": True,
        "status": "ok" if owner == "worker" else "warning",
    }


def _database_metrics(session: Session) -> dict[str, Any]:
    try:
        size_bytes = session.execute(
            text("SELECT pg_database_size(current_database())")
        ).scalar_one()
        connection_count = session.execute(
            text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
        ).scalar_one()
    except SQLAlchemyError as exc:
        return {"status": "error", "error": type(exc).__name__}
    return {
        "status": "ok",
        "size_bytes": int(size_bytes),
        "connection_count": int(connection_count),
    }


def _disk_status(settings: Settings) -> dict[str, Any]:
    configured_path = Path(settings.backup_directory)
    usage_path = configured_path if configured_path.exists() else Path.cwd()
    usage = shutil.disk_usage(usage_path)
    free_percent = round((usage.free / usage.total) * 100, 2) if usage.total else 0
    used_percent = round(100 - free_percent, 2)
    status = "ok"
    if used_percent >= 85:
        status = "critical"
    elif used_percent >= 70:
        status = "warning"
    return {
        "status": status,
        "path": str(usage_path),
        "total_bytes": usage.total,
        "used_bytes": usage.used,
        "free_bytes": usage.free,
        "used_percent": used_percent,
        "warning_percent": 70,
        "critical_percent": 85,
    }


def _backup_status(settings: Settings, now: datetime) -> dict[str, Any]:
    backup_dir = Path(settings.backup_directory)
    latest = _latest_backup_file(backup_dir)
    latest_age_seconds = None
    if latest is not None:
        modified_at = datetime.fromtimestamp(latest.stat().st_mtime, tz=UTC)
        latest_age_seconds = int((now - modified_at).total_seconds())
    return {
        "directory": str(backup_dir),
        "retention_days": settings.backup_retention_days,
        "offserver_configured": settings.backup_offserver_configured,
        "latest_local_backup": None
        if latest is None
        else {
            "path": str(latest),
            "size_bytes": latest.stat().st_size,
            "age_seconds": latest_age_seconds,
        },
    }


def _source_status(session: Session, settings: Settings, now: datetime) -> dict[str, Any]:
    rows = session.execute(
        select(Source, SourceRuntimeState).outerjoin(
            SourceRuntimeState,
            SourceRuntimeState.source_id == Source.id,
        )
    ).all()
    summary = {status.value: 0 for status in SourceHealthStatus}
    summary["UNKNOWN"] = 0
    stale_after = timedelta(seconds=settings.source_stale_after_seconds)
    stale_sources: list[dict[str, Any]] = []
    for source, state in rows:
        status = (
            SourceHealthStatus.DISABLED.value
            if not source.is_enabled
            else state.health_status.value
            if state is not None
            else "UNKNOWN"
        )
        summary[status] = summary.get(status, 0) + 1
        last_success = (
            _aware_datetime(state.last_success_at) if state and state.last_success_at else None
        )
        tracks_runtime_success = (
            source.supports_discovery or source.supports_market_scan or source.supports_detail_fetch
        )
        if (
            source.is_enabled
            and tracks_runtime_success
            and (last_success is None or now - last_success > stale_after)
        ):
            stale_sources.append(
                {
                    "source_id": str(source.id),
                    "source_code": source.code,
                    "last_success_at": last_success.isoformat() if last_success else None,
                }
            )
    return {
        "summary": summary,
        "stale_after_seconds": settings.source_stale_after_seconds,
        "stale_sources": stale_sources,
    }


def _job_status(session: Session, settings: Settings, now: datetime) -> dict[str, Any]:
    stale_cutoff = now - timedelta(seconds=settings.stale_job_timeout_seconds)
    recent_cutoff = now - timedelta(hours=24)
    stale_running_count = session.scalar(
        select(func.count())
        .select_from(JobRun)
        .where(JobRun.status == "RUNNING", JobRun.started_at < stale_cutoff)
    )
    failed_recent_count = session.scalar(
        select(func.count())
        .select_from(JobRun)
        .where(JobRun.status == "FAILED", JobRun.started_at >= recent_cutoff)
    )
    running_count = session.scalar(
        select(func.count()).select_from(JobRun).where(JobRun.status == "RUNNING")
    )
    return {
        "running_count": int(running_count or 0),
        "stale_running_count": int(stale_running_count or 0),
        "failed_last_24h": int(failed_recent_count or 0),
        "stale_after_seconds": settings.stale_job_timeout_seconds,
    }


def _analysis_status(session: Session) -> dict[str, Any]:
    failed_count = _analysis_state_count(session, AnalysisStatus.FAILED)
    stale_count = _analysis_state_count(session, AnalysisStatus.STALE)
    pending_count = _analysis_state_count(session, AnalysisStatus.PENDING)
    return {
        "failed_state_count": failed_count,
        "stale_state_count": stale_count,
        "pending_state_count": pending_count,
    }


def _analysis_state_count(session: Session, status: AnalysisStatus) -> int:
    columns = [
        PropertyAnalysisState.features_status,
        PropertyAnalysisState.matching_status,
        PropertyAnalysisState.comparable_status,
        PropertyAnalysisState.valuation_status,
        PropertyAnalysisState.liquidity_status,
        PropertyAnalysisState.fast_sale_status,
        PropertyAnalysisState.llm_status,
        PropertyAnalysisState.seller_status,
        PropertyAnalysisState.risk_status,
        PropertyAnalysisState.deal_status,
        PropertyAnalysisState.opportunity_status,
    ]
    return int(
        session.scalar(
            select(func.count())
            .select_from(PropertyAnalysisState)
            .where(or_(*(column == status for column in columns)))
        )
        or 0
    )


def _alert_status(session: Session) -> dict[str, Any]:
    rows = session.execute(
        select(Alert.alert_type, Alert.status, func.count())
        .group_by(Alert.alert_type, Alert.status)
        .order_by(Alert.alert_type.asc(), Alert.status.asc())
    ).all()
    summary = {
        alert_type.value: {status.value: 0 for status in AlertStatus} for alert_type in AlertType
    }
    for alert_type, status, count in rows:
        summary[alert_type.value][status.value] = int(count)
    return summary


def _latest_backup_file(backup_dir: Path) -> Path | None:
    if not backup_dir.exists() or not backup_dir.is_dir():
        return None
    candidates = [path for path in backup_dir.glob(BACKUP_FILE_PATTERN) if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _cors_origins(settings: Settings) -> list[str]:
    return [origin.strip() for origin in settings.cors_allowed_origins.split(",") if origin.strip()]


def _alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return config


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _main() -> None:
    with SessionLocal() as session:
        print(json.dumps(build_operations_status(session), sort_keys=True, default=str))


if __name__ == "__main__":
    _main()
