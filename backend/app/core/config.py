from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_env: str = Field(default="development", alias="APP_ENV")
    app_base_url: str = Field(default="http://localhost:8000", alias="APP_BASE_URL")
    app_version: str = Field(default="0.1.0", alias="APP_VERSION")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="text", alias="LOG_FORMAT")
    log_file: str | None = Field(default=None, alias="LOG_FILE")
    log_max_bytes: int = Field(default=10_485_760, alias="LOG_MAX_BYTES")
    log_backup_count: int = Field(default=5, alias="LOG_BACKUP_COUNT")
    api_access_token: str | None = Field(default=None, alias="API_ACCESS_TOKEN")
    cors_allowed_origins: str = Field(
        default="http://127.0.0.1:5173,http://localhost:5173",
        alias="CORS_ALLOWED_ORIGINS",
    )

    database_url: str = Field(
        default=(
            "postgresql+psycopg://distressed_property_radar:change-me-local-only"
            "@localhost:55432/distressed_property_radar"
        ),
        alias="DATABASE_URL",
    )
    database_pool_size: int = Field(default=5, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=5, alias="DATABASE_MAX_OVERFLOW")
    database_connect_timeout_seconds: int = Field(
        default=5,
        alias="DATABASE_CONNECT_TIMEOUT_SECONDS",
    )
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    llm_model: str = Field(default="dpr-structured-extractor-v1", alias="LLM_MODEL")
    telegram_bot_token: str | None = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = Field(default=None, alias="TELEGRAM_CHAT_ID")
    telegram_api_base_url: str = Field(
        default="https://api.telegram.org",
        alias="TELEGRAM_API_BASE_URL",
    )
    scheduler_owner: str = Field(default="worker", alias="SCHEDULER_OWNER")
    stale_job_timeout_seconds: int = Field(default=7200, alias="STALE_JOB_TIMEOUT_SECONDS")
    source_stale_after_seconds: int = Field(default=86400, alias="SOURCE_STALE_AFTER_SECONDS")
    operational_alert_cooldown_seconds: int = Field(
        default=21600,
        alias="OPERATIONAL_ALERT_COOLDOWN_SECONDS",
    )
    backup_directory: str = Field(default="backups", alias="BACKUP_DIRECTORY")
    backup_retention_days: int = Field(default=14, alias="BACKUP_RETENTION_DAYS")
    backup_offserver_configured: bool = Field(
        default=False,
        alias="BACKUP_OFFSERVER_CONFIGURED",
    )
    backup_command_timeout_seconds: int = Field(
        default=3600,
        alias="BACKUP_COMMAND_TIMEOUT_SECONDS",
    )
    pg_dump_path: str = Field(default="pg_dump", alias="PG_DUMP_PATH")
    pg_restore_path: str = Field(default="pg_restore", alias="PG_RESTORE_PATH")
    psql_path: str = Field(default="psql", alias="PSQL_PATH")
    raw_record_retention_days: int = Field(default=90, alias="RAW_RECORD_RETENTION_DAYS")
    worker_poll_interval_seconds: int = Field(default=300, alias="WORKER_POLL_INTERVAL_SECONDS")
    worker_fast_discovery_interval_seconds: int = Field(
        default=1800,
        alias="WORKER_FAST_DISCOVERY_INTERVAL_SECONDS",
    )
    four_zida_timeout_seconds: float = Field(default=20.0, alias="FOUR_ZIDA_TIMEOUT_SECONDS")
    four_zida_retry_count: int = Field(default=2, alias="FOUR_ZIDA_RETRY_COUNT")
    four_zida_min_request_delay_seconds: float = Field(
        default=0.2,
        alias="FOUR_ZIDA_MIN_REQUEST_DELAY_SECONDS",
    )
    four_zida_max_concurrency: int = Field(default=1, alias="FOUR_ZIDA_MAX_CONCURRENCY")
    four_zida_max_pages_per_market: int = Field(
        default=1,
        alias="FOUR_ZIDA_MAX_PAGES_PER_MARKET",
    )
    nekretnine_rs_timeout_seconds: float = Field(
        default=20.0,
        alias="NEKRETNINE_RS_TIMEOUT_SECONDS",
    )
    nekretnine_rs_retry_count: int = Field(default=2, alias="NEKRETNINE_RS_RETRY_COUNT")
    nekretnine_rs_min_request_delay_seconds: float = Field(
        default=0.2,
        alias="NEKRETNINE_RS_MIN_REQUEST_DELAY_SECONDS",
    )
    nekretnine_rs_max_concurrency: int = Field(
        default=1,
        alias="NEKRETNINE_RS_MAX_CONCURRENCY",
    )
    nekretnine_rs_max_pages_per_market: int = Field(
        default=1,
        alias="NEKRETNINE_RS_MAX_PAGES_PER_MARKET",
    )

    model_config = SettingsConfigDict(
        env_file=str(_REPOSITORY_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
