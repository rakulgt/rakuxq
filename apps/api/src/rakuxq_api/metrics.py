from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .domain import RecognitionResult, RecognitionStatus


@dataclass(frozen=True, slots=True)
class PublicEvent:
    occurred_at: str
    status: str
    fen: str
    confidence: float
    duration_ms: int


class PublicMetricsStore:
    """Persistent anonymous counters plus a rolling public interaction window."""

    def __init__(self, database: str | Path, event_hours: int = 72):
        self.database = Path(database)
        self.event_hours = event_hours
        self._lock = threading.Lock()

    def initialize(self) -> None:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS public_events (
                    source_id TEXT PRIMARY KEY,
                    occurred_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    fen TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    duration_ms INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_public_events_occurred_at
                    ON public_events(occurred_at DESC);

                CREATE TABLE IF NOT EXISTS public_totals (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    successful INTEGER NOT NULL DEFAULT 0,
                    accepted INTEGER NOT NULL DEFAULT 0,
                    review_required INTEGER NOT NULL DEFAULT 0,
                    first_seen_at TEXT,
                    last_seen_at TEXT
                );
                INSERT OR IGNORE INTO public_totals(singleton) VALUES (1);
                """
            )

    def record(self, result: RecognitionResult, occurred_at: datetime | None = None) -> bool:
        if result.fen is None or result.status not in {
            RecognitionStatus.ACCEPTED,
            RecognitionStatus.REVIEW_REQUIRED,
        }:
            return False
        return self._record_values(
            source_id=result.request_id,
            occurred_at=occurred_at or datetime.now(UTC),
            status=result.status.value,
            fen=result.fen,
            confidence=result.confidence,
            duration_ms=result.prediction.elapsed_ms if result.prediction else 0,
        )

    def import_audit_directory(self, audit_root: str | Path) -> int:
        root = Path(audit_root)
        if not root.exists():
            return 0
        imported = 0
        for metadata_path in sorted(root.glob("*/interaction.json")):
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                response = metadata["response"]
                status = str(response["recognition_status"])
                fen = response["fen"]
                source_id = response["request_id"]
                if status not in {"accepted", "review_required"}:
                    continue
                if not isinstance(fen, str) or not isinstance(source_id, str):
                    continue
                occurred_at = datetime.fromisoformat(
                    str(metadata["received_at"]).replace("Z", "+00:00")
                )
                if self._record_values(
                    source_id=source_id,
                    occurred_at=occurred_at,
                    status=status,
                    fen=self._simplified_fen(fen),
                    confidence=float(response["confidence"] or 0),
                    duration_ms=int(metadata["duration_ms"] or 0),
                ):
                    imported += 1
            except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError):
                continue
        return imported

    def _record_values(
        self,
        *,
        source_id: str,
        occurred_at: datetime,
        status: str,
        fen: str,
        confidence: float,
        duration_ms: int,
    ) -> bool:
        timestamp = self._timestamp(occurred_at)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO public_events(
                    source_id, occurred_at, status, fen, confidence, duration_ms
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    timestamp,
                    status,
                    fen,
                    confidence,
                    duration_ms,
                ),
            )
            if cursor.rowcount != 1:
                return False
            accepted = int(status == RecognitionStatus.ACCEPTED.value)
            review_required = int(status == RecognitionStatus.REVIEW_REQUIRED.value)
            connection.execute(
                """
                UPDATE public_totals
                SET successful = successful + 1,
                    accepted = accepted + ?,
                    review_required = review_required + ?,
                    first_seen_at = COALESCE(first_seen_at, ?),
                    last_seen_at = ?
                WHERE singleton = 1
                """,
                (accepted, review_required, timestamp, timestamp),
            )
            self._prune_connection(connection, occurred_at)
        return True

    def snapshot(self, limit: int = 60, now: datetime | None = None) -> dict[str, object]:
        current = now or datetime.now(UTC)
        cutoff = self._timestamp(current - timedelta(hours=self.event_hours))
        with self._lock, self._connect() as connection:
            self._prune_connection(connection, current)
            totals = connection.execute(
                """
                SELECT successful, accepted, review_required, first_seen_at, last_seen_at
                FROM public_totals WHERE singleton = 1
                """
            ).fetchone()
            recent = connection.execute(
                """
                SELECT COUNT(*) AS successful,
                       SUM(status = 'accepted') AS accepted,
                       SUM(status = 'review_required') AS review_required,
                       AVG(duration_ms) AS average_duration_ms
                FROM public_events WHERE occurred_at >= ?
                """,
                (cutoff,),
            ).fetchone()
            rows = connection.execute(
                """
                SELECT occurred_at, status, fen, confidence, duration_ms
                FROM public_events
                WHERE occurred_at >= ?
                ORDER BY occurred_at DESC
                LIMIT ?
                """,
                (cutoff, max(1, min(limit, 200))),
            ).fetchall()
            hourly_rows = connection.execute(
                """
                SELECT substr(occurred_at, 1, 13) || ':00:00Z' AS hour,
                       COUNT(*) AS interactions
                FROM public_events
                WHERE occurred_at >= ?
                GROUP BY hour
                ORDER BY hour ASC
                """,
                (cutoff,),
            ).fetchall()

        lifetime_successful = int(totals["successful"] if totals else 0)
        lifetime_accepted = int(totals["accepted"] if totals else 0)
        recent_successful = int(recent["successful"] if recent else 0)
        recent_accepted = int((recent["accepted"] if recent else 0) or 0)
        return {
            "generated_at": self._timestamp(current),
            "recent_window_hours": self.event_hours,
            "lifetime": {
                "successful": lifetime_successful,
                "accepted": lifetime_accepted,
                "review_required": int(totals["review_required"] if totals else 0),
                "acceptance_rate": self._rate(lifetime_accepted, lifetime_successful),
                "first_seen_at": totals["first_seen_at"] if totals else None,
                "last_seen_at": totals["last_seen_at"] if totals else None,
            },
            "recent": {
                "successful": recent_successful,
                "accepted": recent_accepted,
                "review_required": int((recent["review_required"] if recent else 0) or 0),
                "acceptance_rate": self._rate(recent_accepted, recent_successful),
                "average_duration_ms": round(
                    float((recent["average_duration_ms"] if recent else 0) or 0)
                ),
            },
            "hourly": [dict(row) for row in hourly_rows],
            "events": [dict(row) for row in rows],
        }

    def _prune_connection(self, connection: sqlite3.Connection, now: datetime) -> None:
        cutoff = self._timestamp(now - timedelta(hours=self.event_hours))
        connection.execute("DELETE FROM public_events WHERE occurred_at < ?", (cutoff,))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    @staticmethod
    def _timestamp(value: datetime) -> str:
        return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    @staticmethod
    def _rate(part: int, total: int) -> float:
        return round(part / total * 100, 1) if total else 0.0

    @staticmethod
    def _simplified_fen(fen: str) -> str:
        fields = fen.split()
        return " ".join(fields[:2]) if len(fields) >= 2 else fen
