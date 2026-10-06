from __future__ import annotations

import base64
import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .domain import RecognitionResult, RecognitionStatus
from .geo import GeoLocation


class InvalidEventCursor(ValueError):
    pass


class PublicMetricsStore:
    """Persistent anonymous counters plus an age- and count-bounded event stream."""

    def __init__(
        self,
        database: str | Path,
        event_hours: int = 720,
        max_events: int = 100_000,
    ):
        self.database = Path(database)
        self.event_hours = max(1, event_hours)
        self.max_events = max(1, max_events)
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
                    duration_ms INTEGER NOT NULL,
                    country_code TEXT,
                    country_name TEXT,
                    region_name TEXT,
                    city_name TEXT,
                    latitude REAL,
                    longitude REAL
                );

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
            self._migrate_event_columns(connection)
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_public_events_occurred_at
                    ON public_events(occurred_at DESC);
                CREATE INDEX IF NOT EXISTS idx_public_events_order
                    ON public_events(occurred_at DESC, source_id DESC);
                DROP INDEX IF EXISTS idx_public_events_location;
                CREATE INDEX IF NOT EXISTS idx_public_events_country
                    ON public_events(country_code);
                """
            )
            connection.execute(
                """
                UPDATE public_events
                SET region_name = NULL, city_name = NULL,
                    latitude = NULL, longitude = NULL
                WHERE region_name IS NOT NULL OR city_name IS NOT NULL
                   OR latitude IS NOT NULL OR longitude IS NOT NULL
                """
            )
            self._prune_connection(connection, datetime.now(UTC))

    def record(
        self,
        result: RecognitionResult,
        occurred_at: datetime | None = None,
        location: GeoLocation | None = None,
    ) -> bool:
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
            location=location,
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
                    location=None,
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
        location: GeoLocation | None,
    ) -> bool:
        timestamp = self._timestamp(occurred_at)
        geo = location or GeoLocation()
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO public_events(
                    source_id, occurred_at, status, fen, confidence, duration_ms,
                    country_code, country_name, region_name, city_name, latitude, longitude
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    timestamp,
                    status,
                    fen,
                    confidence,
                    duration_ms,
                    geo.country_code,
                    geo.country_name,
                    None,
                    None,
                    None,
                    None,
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
        hourly_cutoff = self._timestamp(current - timedelta(hours=min(self.event_hours, 72)))
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
                       AVG(duration_ms) AS average_duration_ms,
                       SUM(country_code IS NOT NULL) AS located
                FROM public_events WHERE occurred_at >= ?
                """,
                (cutoff,),
            ).fetchone()
            rows = connection.execute(
                """
                SELECT occurred_at, status, fen, confidence, duration_ms,
                       country_code, country_name
                FROM public_events
                WHERE occurred_at >= ?
                ORDER BY occurred_at DESC, source_id DESC
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
                (hourly_cutoff,),
            ).fetchall()
            daily_rows = connection.execute(
                """
                SELECT substr(occurred_at, 1, 10) AS day,
                       COUNT(*) AS interactions
                FROM public_events
                WHERE occurred_at >= ?
                GROUP BY day
                ORDER BY day ASC
                """,
                (cutoff,),
            ).fetchall()
            location_rows = connection.execute(
                """
                SELECT country_code, country_name, COUNT(*) AS interactions
                FROM public_events
                WHERE occurred_at >= ? AND country_code IS NOT NULL
                GROUP BY country_code, country_name
                ORDER BY interactions DESC, country_code ASC
                LIMIT 250
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
            "max_retained_events": self.max_events,
            "retained_events": recent_successful,
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
                "located": int((recent["located"] if recent else 0) or 0),
            },
            "hourly": [dict(row) for row in hourly_rows],
            "daily": [dict(row) for row in daily_rows],
            "locations": [dict(row) for row in location_rows],
            "events": [self._public_event(row) for row in rows],
        }

    def event_page(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, object]:
        current = now or datetime.now(UTC)
        page_size = max(1, min(limit, 100))
        anchor, offset = self._decode_cursor(cursor, current)
        cutoff = self._timestamp(current - timedelta(hours=self.event_hours))
        with self._lock, self._connect() as connection:
            self._prune_connection(connection, current)
            rows = connection.execute(
                """
                SELECT occurred_at, status, fen, confidence, duration_ms,
                       country_code, country_name
                FROM public_events
                WHERE occurred_at >= ? AND occurred_at <= ?
                ORDER BY occurred_at DESC, source_id DESC
                LIMIT ? OFFSET ?
                """,
                (cutoff, anchor, page_size + 1, offset),
            ).fetchall()
            retained = int(
                connection.execute(
                    "SELECT COUNT(*) FROM public_events WHERE occurred_at >= ?",
                    (cutoff,),
                ).fetchone()[0]
            )
        has_more = len(rows) > page_size and offset + page_size < self.max_events
        page_rows = rows[:page_size]
        next_cursor = (
            self._encode_cursor(anchor, offset + len(page_rows)) if has_more else None
        )
        return {
            "generated_at": self._timestamp(current),
            "recent_window_hours": self.event_hours,
            "max_retained_events": self.max_events,
            "retained_events": retained,
            "page_size": page_size,
            "offset": offset,
            "events": [self._public_event(row) for row in page_rows],
            "has_more": has_more,
            "next_cursor": next_cursor,
        }

    def _prune_connection(self, connection: sqlite3.Connection, now: datetime) -> None:
        cutoff = self._timestamp(now - timedelta(hours=self.event_hours))
        connection.execute("DELETE FROM public_events WHERE occurred_at < ?", (cutoff,))
        retained = int(connection.execute("SELECT COUNT(*) FROM public_events").fetchone()[0])
        overflow = retained - self.max_events
        if overflow > 0:
            connection.execute(
                """
                DELETE FROM public_events
                WHERE rowid IN (
                    SELECT rowid FROM public_events
                    ORDER BY occurred_at ASC, source_id ASC
                    LIMIT ?
                )
                """,
                (overflow,),
            )

    @staticmethod
    def _migrate_event_columns(connection: sqlite3.Connection) -> None:
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(public_events)").fetchall()
        }
        additions = {
            "country_code": "TEXT",
            "country_name": "TEXT",
            "region_name": "TEXT",
            "city_name": "TEXT",
            "latitude": "REAL",
            "longitude": "REAL",
        }
        for name, sql_type in additions.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE public_events ADD COLUMN {name} {sql_type}")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def _decode_cursor(self, cursor: str | None, current: datetime) -> tuple[str, int]:
        if not cursor:
            return self._timestamp(current), 0
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
            anchor = str(payload["before"])
            offset = int(payload["offset"])
            parsed = datetime.fromisoformat(anchor.replace("Z", "+00:00"))
            normalized = self._timestamp(parsed)
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidEventCursor("invalid event cursor") from exc
        if offset < 0 or offset >= self.max_events or normalized != anchor:
            raise InvalidEventCursor("invalid event cursor")
        return anchor, offset

    @staticmethod
    def _encode_cursor(anchor: str, offset: int) -> str:
        payload = json.dumps(
            {"before": anchor, "offset": offset},
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    @staticmethod
    def _public_event(row: sqlite3.Row) -> dict[str, object]:
        location: dict[str, object] | None = None
        if row["country_code"] or row["country_name"]:
            location = {
                "country_code": row["country_code"],
                "country": row["country_name"],
            }
        return {
            "occurred_at": row["occurred_at"],
            "status": row["status"],
            "fen": row["fen"],
            "confidence": row["confidence"],
            "duration_ms": row["duration_ms"],
            "location": location,
        }

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
