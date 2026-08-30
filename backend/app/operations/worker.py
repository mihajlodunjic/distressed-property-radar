from __future__ import annotations

import argparse
import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal, database_is_reachable
from app.ingestion.four_zida_discovery import (
    CrawlMode,
    IngestionSummary,
    run_scheduled_four_zida_crawl,
)
from app.operations.maintenance import MaintenanceResult, run_operational_maintenance
from app.opportunities.opportunity_engine import AlertDeliveryAttempt, send_due_telegram_alerts
from app.opportunities.telegram import HttpTelegramSender, TelegramSender
from app.sources.four_zida.adapter import FourZidaAdapter, FourZidaConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerIterationResult:
    maintenance: MaintenanceResult
    crawl: dict[str, Any] | None
    alert_delivery_attempts: int

    def to_jsonable(self) -> dict[str, Any]:
        return {
            "maintenance": self.maintenance.to_jsonable(),
            "crawl": self.crawl,
            "alert_delivery_attempts": self.alert_delivery_attempts,
        }


def run_worker_iteration(
    session: Session,
    *,
    settings: Settings | None = None,
    mode: CrawlMode = CrawlMode.FAST_DISCOVERY,
    skip_crawl: bool = False,
    send_alerts: bool = False,
    sender: TelegramSender | None = None,
    commit: bool = False,
) -> WorkerIterationResult:
    effective_settings = settings or get_settings()
    maintenance = run_operational_maintenance(
        session,
        settings=effective_settings,
        commit=False,
    )
    crawl_summary: IngestionSummary | None = None
    if not skip_crawl:
        adapter = FourZidaAdapter(config=_four_zida_config(effective_settings))
        crawl_summary = run_scheduled_four_zida_crawl(
            session,
            mode=mode,
            interval_seconds=effective_settings.worker_fast_discovery_interval_seconds,
            adapter=adapter,
            max_pages_per_market=effective_settings.four_zida_max_pages_per_market,
            commit=False,
        )
    attempts: list[AlertDeliveryAttempt] = []
    if send_alerts:
        attempts = send_due_telegram_alerts(
            session,
            sender or HttpTelegramSender.from_settings(effective_settings),
        )
    if commit:
        session.commit()
    return WorkerIterationResult(
        maintenance=maintenance,
        crawl=crawl_summary.to_jsonable() if crawl_summary is not None else None,
        alert_delivery_attempts=len(attempts),
    )


def run_worker_loop(
    *,
    settings: Settings | None = None,
    mode: CrawlMode = CrawlMode.FAST_DISCOVERY,
    poll_interval_seconds: int | None = None,
    skip_crawl: bool = False,
    send_alerts: bool = False,
) -> None:
    effective_settings = settings or get_settings()
    interval = (
        poll_interval_seconds
        if poll_interval_seconds is not None
        else effective_settings.worker_poll_interval_seconds
    )
    logger.info(
        "worker startup environment=%s app_version=%s process_type=worker database_reachable=%s",
        effective_settings.app_env,
        effective_settings.app_version,
        database_is_reachable(),
    )
    while True:
        try:
            with SessionLocal() as session:
                result = run_worker_iteration(
                    session,
                    settings=effective_settings,
                    mode=mode,
                    skip_crawl=skip_crawl,
                    send_alerts=send_alerts,
                    commit=True,
                )
            logger.info("worker iteration completed result=%s", result.to_jsonable())
        except SQLAlchemyError:
            logger.exception("worker iteration database failure")
        except Exception:
            logger.exception("worker iteration failed")
        time.sleep(max(interval, 1))


def _four_zida_config(settings: Settings) -> FourZidaConfig:
    return FourZidaConfig(
        timeout_seconds=settings.four_zida_timeout_seconds,
        retry_count=settings.four_zida_retry_count,
        min_request_delay_seconds=settings.four_zida_min_request_delay_seconds,
        max_concurrency=settings.four_zida_max_concurrency,
    )


def _mode_from_cli(value: str) -> CrawlMode:
    return CrawlMode(value.replace("-", "_").upper())


def _main(argv: Sequence[str] | None = None) -> None:
    settings = get_settings()
    configure_logging(
        settings.log_level,
        log_format=settings.log_format,
        log_file=settings.log_file,
        log_max_bytes=settings.log_max_bytes,
        log_backup_count=settings.log_backup_count,
    )
    parser = argparse.ArgumentParser(description="Run the Distressed Property Radar worker.")
    parser.add_argument(
        "--mode",
        choices=["fast-discovery", "active-market-scan", "deep-reconciliation"],
        default="fast-discovery",
    )
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--skip-crawl", action="store_true")
    parser.add_argument("--send-alerts", action="store_true")
    parser.add_argument(
        "--poll-interval-seconds",
        type=int,
        default=settings.worker_poll_interval_seconds,
    )
    args = parser.parse_args(argv)
    mode = _mode_from_cli(args.mode)

    if args.once:
        with SessionLocal() as session:
            result = run_worker_iteration(
                session,
                settings=settings,
                mode=mode,
                skip_crawl=args.skip_crawl,
                send_alerts=args.send_alerts,
                commit=True,
            )
        print(json.dumps(result.to_jsonable(), sort_keys=True))
        return

    try:
        run_worker_loop(
            settings=settings,
            mode=mode,
            poll_interval_seconds=args.poll_interval_seconds,
            skip_crawl=args.skip_crawl,
            send_alerts=args.send_alerts,
        )
    except KeyboardInterrupt:
        logger.info("worker shutdown requested")


if __name__ == "__main__":
    _main()
