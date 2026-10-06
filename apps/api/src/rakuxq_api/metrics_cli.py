from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .metrics import PublicMetricsStore


def backup(database: Path, output_directory: Path, keep_days: int) -> Path:
    if not database.is_file():
        raise FileNotFoundError(database)
    output_directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    destination = output_directory / f"public-metrics-{now:%Y%m%d-%H%M%S}.sqlite3"
    temporary = destination.with_suffix(".sqlite3.tmp")
    try:
        source_uri = f"{database.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(source_uri, uri=True)) as source, closing(
            sqlite3.connect(temporary)
        ) as target:
            source.backup(target)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    destination.chmod(0o600)

    cutoff = now - timedelta(days=keep_days)
    for candidate in output_directory.glob("public-metrics-*.sqlite3"):
        modified_at = datetime.fromtimestamp(candidate.stat().st_mtime, UTC)
        failed_or_expired = candidate.stat().st_size == 0 or modified_at < cutoff
        if candidate != destination and failed_or_expired:
            candidate.unlink()
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up RakuXQ anonymous metrics.")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path)
    parser.add_argument("--keep-days", type=int, default=30)
    parser.add_argument("--event-hours", type=int, default=720)
    parser.add_argument("--max-events", type=int, default=100_000)
    parser.add_argument("--prune-only", action="store_true")
    arguments = parser.parse_args()
    if arguments.keep_days < 1:
        parser.error("--keep-days must be at least 1")
    if arguments.event_hours < 1 or arguments.max_events < 1:
        parser.error("retention values must be at least 1")
    store = PublicMetricsStore(
        arguments.database,
        event_hours=arguments.event_hours,
        max_events=arguments.max_events,
    )
    store.initialize()
    if arguments.prune_only:
        return
    if arguments.output_directory is None:
        parser.error("--output-directory is required unless --prune-only is used")
    print(backup(arguments.database, arguments.output_directory, arguments.keep_days))


if __name__ == "__main__":
    main()
