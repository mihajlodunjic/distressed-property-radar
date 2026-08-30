from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.engine import URL, make_url

from app.core.config import get_settings

BACKUP_FILE_PREFIX = "dpr-postgres"
BACKUP_FILE_PATTERN = f"{BACKUP_FILE_PREFIX}-*.dump"

Runner = Callable[
    [Sequence[str], Mapping[str, str], int],
    subprocess.CompletedProcess[str],
]


class BackupCommandError(RuntimeError):
    def __init__(self, operation: str, returncode: int, stderr: str) -> None:
        super().__init__(f"{operation} failed with exit code {returncode}")
        self.operation = operation
        self.returncode = returncode
        self.stderr = stderr


@dataclass(frozen=True)
class BackupResult:
    backup_path: str
    size_bytes: int
    created_at: str
    pruned_count: int = 0


@dataclass(frozen=True)
class RestoreResult:
    backup_path: str
    restored: bool
    verified: bool = False


@dataclass(frozen=True)
class BackupRetentionResult:
    cutoff_at: str
    matched_count: int
    deleted_count: int
    dry_run: bool


def create_database_backup(
    *,
    database_url: str,
    output_dir: str | Path,
    pg_dump_path: str = "pg_dump",
    retention_days: int | None = None,
    timeout_seconds: int = 3600,
    now: datetime | None = None,
    runner: Runner | None = None,
) -> BackupResult:
    created_at = _aware_datetime(now or datetime.now(UTC))
    backup_dir = Path(output_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{BACKUP_FILE_PREFIX}-{created_at.strftime('%Y%m%dT%H%M%SZ')}.dump"
    connection = _connection_options(database_url)
    command = [
        pg_dump_path,
        "-Fc",
        "--no-owner",
        "--no-privileges",
        "-h",
        connection.host,
        "-p",
        connection.port,
        "-U",
        connection.username,
        "-d",
        connection.database,
        "-f",
        str(backup_path),
    ]
    _run(command, connection.env, timeout_seconds, "pg_dump", runner)
    pruned_count = 0
    if retention_days is not None:
        pruned_count = prune_backup_files(
            backup_dir,
            retention_days=retention_days,
            now=created_at,
            dry_run=False,
        ).deleted_count
    return BackupResult(
        backup_path=str(backup_path),
        size_bytes=backup_path.stat().st_size if backup_path.exists() else 0,
        created_at=created_at.isoformat(),
        pruned_count=pruned_count,
    )


def restore_database_backup(
    *,
    database_url: str,
    backup_path: str | Path,
    pg_restore_path: str = "pg_restore",
    clean: bool = False,
    timeout_seconds: int = 3600,
    runner: Runner | None = None,
) -> RestoreResult:
    backup = Path(backup_path)
    if not backup.is_file():
        raise FileNotFoundError(str(backup))
    connection = _connection_options(database_url)
    command = [
        pg_restore_path,
        "--no-owner",
        "--no-privileges",
        "--single-transaction",
        "-h",
        connection.host,
        "-p",
        connection.port,
        "-U",
        connection.username,
        "-d",
        connection.database,
    ]
    if clean:
        command.extend(["--clean", "--if-exists"])
    command.append(str(backup))
    _run(command, connection.env, timeout_seconds, "pg_restore", runner)
    return RestoreResult(backup_path=str(backup), restored=True)


def verify_database_restore(
    *,
    database_url: str,
    backup_path: str | Path,
    pg_restore_path: str = "pg_restore",
    psql_path: str = "psql",
    timeout_seconds: int = 3600,
    runner: Runner | None = None,
) -> RestoreResult:
    restore_database_backup(
        database_url=database_url,
        backup_path=backup_path,
        pg_restore_path=pg_restore_path,
        clean=True,
        timeout_seconds=timeout_seconds,
        runner=runner,
    )
    connection = _connection_options(database_url)
    command = [
        psql_path,
        "-v",
        "ON_ERROR_STOP=1",
        "-h",
        connection.host,
        "-p",
        connection.port,
        "-U",
        connection.username,
        "-d",
        connection.database,
        "-c",
        "SELECT 1; SELECT postgis_version(); SELECT count(*) FROM alembic_version;",
    ]
    _run(command, connection.env, timeout_seconds, "restore verification", runner)
    return RestoreResult(backup_path=str(backup_path), restored=True, verified=True)


def prune_backup_files(
    output_dir: str | Path,
    *,
    retention_days: int,
    now: datetime | None = None,
    dry_run: bool = True,
) -> BackupRetentionResult:
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")

    observed_at = _aware_datetime(now or datetime.now(UTC))
    cutoff = observed_at - timedelta(days=retention_days)
    backup_dir = Path(output_dir)
    matched = [
        path
        for path in backup_dir.glob(BACKUP_FILE_PATTERN)
        if path.is_file() and _file_modified_at(path) < cutoff
    ]
    deleted_count = 0
    if not dry_run:
        for path in matched:
            path.unlink()
            deleted_count += 1
    return BackupRetentionResult(
        cutoff_at=cutoff.isoformat(),
        matched_count=len(matched),
        deleted_count=deleted_count,
        dry_run=dry_run,
    )


@dataclass(frozen=True)
class _ConnectionOptions:
    host: str
    port: str
    username: str
    database: str
    env: dict[str, str]


def _connection_options(database_url: str) -> _ConnectionOptions:
    url = make_url(database_url)
    if not isinstance(url, URL):
        raise ValueError("Invalid DATABASE_URL")
    if not url.database:
        raise ValueError("DATABASE_URL must include a database name")
    if not url.username:
        raise ValueError("DATABASE_URL must include a username")
    env = dict(os.environ)
    if url.password:
        env["PGPASSWORD"] = url.password
    return _ConnectionOptions(
        host=url.host or "localhost",
        port=str(url.port or 5432),
        username=url.username,
        database=url.database,
        env=env,
    )


def _run(
    command: Sequence[str],
    env: Mapping[str, str],
    timeout_seconds: int,
    operation: str,
    runner: Runner | None,
) -> subprocess.CompletedProcess[str]:
    active_runner = runner or _subprocess_runner
    result = active_runner(command, env, timeout_seconds)
    if result.returncode != 0:
        raise BackupCommandError(operation, result.returncode, result.stderr)
    return result


def _subprocess_runner(
    command: Sequence[str],
    env: Mapping[str, str],
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        env=dict(env),
        timeout=timeout_seconds,
        check=False,
        capture_output=True,
        text=True,
    )


def _file_modified_at(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _main(argv: Sequence[str] | None = None) -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Database backup and restore operations.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--database-url", default=settings.database_url)
    create_parser.add_argument("--output-dir", default=settings.backup_directory)
    create_parser.add_argument("--pg-dump-path", default=settings.pg_dump_path)
    create_parser.add_argument("--retention-days", type=int, default=settings.backup_retention_days)
    create_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=settings.backup_command_timeout_seconds,
    )

    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("backup_path")
    restore_parser.add_argument("--database-url", default=settings.database_url)
    restore_parser.add_argument("--pg-restore-path", default=settings.pg_restore_path)
    restore_parser.add_argument("--clean", action="store_true")
    restore_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=settings.backup_command_timeout_seconds,
    )

    verify_parser = subparsers.add_parser("verify-restore")
    verify_parser.add_argument("backup_path")
    verify_parser.add_argument("--database-url", default=settings.database_url)
    verify_parser.add_argument("--pg-restore-path", default=settings.pg_restore_path)
    verify_parser.add_argument("--psql-path", default=settings.psql_path)
    verify_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=settings.backup_command_timeout_seconds,
    )

    prune_parser = subparsers.add_parser("prune")
    prune_parser.add_argument("--output-dir", default=settings.backup_directory)
    prune_parser.add_argument("--retention-days", type=int, default=settings.backup_retention_days)
    prune_parser.add_argument("--apply", action="store_true")

    args = parser.parse_args(argv)
    result: Any
    if args.command == "create":
        result = create_database_backup(
            database_url=args.database_url,
            output_dir=args.output_dir,
            pg_dump_path=args.pg_dump_path,
            retention_days=args.retention_days,
            timeout_seconds=args.timeout_seconds,
            runner=_subprocess_runner,
        )
    elif args.command == "restore":
        result = restore_database_backup(
            database_url=args.database_url,
            backup_path=args.backup_path,
            pg_restore_path=args.pg_restore_path,
            clean=args.clean,
            timeout_seconds=args.timeout_seconds,
            runner=_subprocess_runner,
        )
    elif args.command == "verify-restore":
        result = verify_database_restore(
            database_url=args.database_url,
            backup_path=args.backup_path,
            pg_restore_path=args.pg_restore_path,
            psql_path=args.psql_path,
            timeout_seconds=args.timeout_seconds,
            runner=_subprocess_runner,
        )
    else:
        result = prune_backup_files(
            args.output_dir,
            retention_days=args.retention_days,
            dry_run=not args.apply,
        )
    print(json.dumps(asdict(result), sort_keys=True))


if __name__ == "__main__":
    _main()
