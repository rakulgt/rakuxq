from __future__ import annotations

import argparse
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path


def backup(database: Path, output_directory: Path, keep_days: int) -> Path:
    if not database.is_file():
        raise FileNotFoundError(database)
    output_directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    destination = output_directory / f"public-metrics-{now:%Y%m%d-%H%M%S}.sqlite3"
    with sqlite3.connect(database) as source, sqlite3.connect(destination) as target:
        source.backup(target)
    destination.chmod(0o600)

    cutoff = now - timedelta(days=keep_days)
    for candidate in output_directory.glob("public-metrics-*.sqlite3"):
        modified_at = datetime.fromtimestamp(candidate.stat().st_mtime, UTC)
        if candidate != destination and modified_at < cutoff:
            candidate.unlink()
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Back up RakuXQ anonymous metrics.")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--keep-days", type=int, default=30)
    arguments = parser.parse_args()
    if arguments.keep_days < 1:
        parser.error("--keep-days must be at least 1")
    print(backup(arguments.database, arguments.output_directory, arguments.keep_days))


if __name__ == "__main__":
    main()
