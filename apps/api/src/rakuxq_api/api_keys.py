from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True, slots=True)
class APIKeyValidation:
    status: str
    key_id: str | None = None
    label: str | None = None
    expires_at: datetime | None = None


class TrialKeyCooldown(RuntimeError):
    def __init__(self, retry_after_seconds: int):
        super().__init__("a trial key is already active for this client")
        self.retry_after_seconds = retry_after_seconds


class TrialKeyCapacity(RuntimeError):
    pass


class APIKeyQuotaUnavailable(RuntimeError):
    def __init__(self, quota: dict[str, int]):
        self.quota = quota


class APIKeyStore:
    def __init__(self, database: str | Path):
        self.database = Path(database)

    def ready(self) -> bool:
        return self.database.is_file()

    def initialize(self) -> None:
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,
                    key_prefix TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS trial_key_issuances (
                    client_fingerprint TEXT PRIMARY KEY,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS api_key_quotas (
                    key_id TEXT PRIMARY KEY REFERENCES api_keys(id),
                    total INTEGER NOT NULL CHECK(total > 0),
                    used INTEGER NOT NULL DEFAULT 0 CHECK(used >= 0 AND used <= total)
                );
                CREATE TABLE IF NOT EXISTS api_key_reservations (
                    id TEXT PRIMARY KEY,
                    key_id TEXT NOT NULL REFERENCES api_key_quotas(key_id),
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS quota_reservation_key
                    ON api_key_reservations(key_id);
                """
            )
        if os.name != "nt":
            self.database.chmod(0o600)

    def create(
        self, label: str, days: int = 365, uses: int | None = None,
    ) -> tuple[str, str, datetime]:
        if not label.strip():
            raise ValueError("label must not be empty")
        if days < 1:
            raise ValueError("days must be positive")
        if uses is not None and (type(uses) is not int or uses < 1):
            raise ValueError("uses must be a positive integer")
        self.initialize()
        now = datetime.now(UTC)
        expires_at = now + timedelta(days=days)
        key_id = f"key_{secrets.token_hex(8)}"
        plaintext = f"rxq_live_{secrets.token_urlsafe(32)}"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO api_keys
                    (id, label, key_hash, key_prefix, created_at, expires_at, revoked_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    key_id,
                    label.strip(),
                    self._hash(plaintext),
                    plaintext[:13],
                    self._format(now),
                    self._format(expires_at),
                ),
            )
            if uses is not None:
                connection.execute(
                    "INSERT INTO api_key_quotas (key_id, total, used) VALUES (?, ?, 0)",
                    (key_id, uses),
                )
        return key_id, plaintext, expires_at

    @staticmethod
    def _quota(connection: sqlite3.Connection, key_id: str) -> dict[str, int] | None:
        row = connection.execute(
            "SELECT total, used FROM api_key_quotas WHERE key_id = ?", (key_id,),
        ).fetchone()
        if row is None:
            return None
        in_flight = connection.execute(
            "SELECT COUNT(*) FROM api_key_reservations WHERE key_id = ?", (key_id,),
        ).fetchone()[0]
        return {"limit": row[0], "used": row[1], "in_flight": in_flight,
                "remaining": row[0] - row[1] - in_flight}

    def quota(self, key_id: str) -> dict[str, int] | None:
        with self._connect() as connection:
            return self._quota(connection, key_id)

    def reserve_usage(self, key_id: str) -> str | None:
        """Reserve before work; concurrent requests cannot spend the same credit."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            quota = self._quota(connection, key_id)
            if quota is None:
                return None  # Existing time-only keys retain their original behavior.
            if quota["remaining"] < 1:
                raise APIKeyQuotaUnavailable(quota)
            reservation = secrets.token_hex(16)
            connection.execute(
                "INSERT INTO api_key_reservations (id, key_id, created_at) VALUES (?, ?, ?)",
                (reservation, key_id, self._format(datetime.now(UTC))),
            )
        return reservation

    def finish_usage(self, key_id: str, reservation: str, success: bool) -> dict[str, int]:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            deleted = connection.execute(
                "DELETE FROM api_key_reservations WHERE id = ? AND key_id = ?",
                (reservation, key_id),
            )
            if deleted.rowcount != 1:
                raise ValueError("Unknown or already settled quota reservation")
            if success:
                connection.execute(
                    "UPDATE api_key_quotas SET used = used + 1 WHERE key_id = ?", (key_id,),
                )
            quota = self._quota(connection, key_id)
            if quota is None:
                raise ValueError("Quota disappeared during settlement")
            return quota

    def issue_trial(
        self,
        client_fingerprint: str,
        minutes: int = 6,
        active_limit: int = 100,
    ) -> tuple[str, datetime]:
        if not client_fingerprint:
            raise ValueError("client fingerprint must not be empty")
        if minutes < 1 or active_limit < 1:
            raise ValueError("trial limits must be positive")
        self.initialize()
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=minutes)
        plaintext = f"rxq_trial_{secrets.token_urlsafe(32)}"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            now_text = self._format(now)
            connection.execute(
                "DELETE FROM trial_key_issuances WHERE expires_at <= ?",
                (now_text,),
            )
            connection.execute(
                "DELETE FROM api_keys WHERE label = 'public-trial' AND expires_at <= ?",
                (now_text,),
            )
            current = connection.execute(
                "SELECT expires_at FROM trial_key_issuances WHERE client_fingerprint = ?",
                (client_fingerprint,),
            ).fetchone()
            if current is not None:
                remaining = max(1, int((self._parse(current[0]) - now).total_seconds()))
                raise TrialKeyCooldown(remaining)
            active = connection.execute(
                """
                SELECT COUNT(*) FROM api_keys
                WHERE label = 'public-trial'
                  AND expires_at > ?
                  AND revoked_at IS NULL
                """,
                (now_text,),
            ).fetchone()[0]
            if active >= active_limit:
                raise TrialKeyCapacity("trial key capacity reached")
            connection.execute(
                """
                INSERT INTO api_keys
                    (id, label, key_hash, key_prefix, created_at, expires_at, revoked_at)
                VALUES (?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    f"trial_{secrets.token_hex(8)}",
                    "public-trial",
                    self._hash(plaintext),
                    plaintext[:13],
                    now_text,
                    self._format(expires_at),
                ),
            )
            connection.execute(
                """
                INSERT INTO trial_key_issuances (client_fingerprint, issued_at, expires_at)
                VALUES (?, ?, ?)
                """,
                (client_fingerprint, now_text, self._format(expires_at)),
            )
        return plaintext, expires_at

    def validate(self, plaintext: str | None) -> APIKeyValidation:
        if not plaintext:
            return APIKeyValidation("missing")
        if not self.ready():
            return APIKeyValidation("store_unavailable")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, label, expires_at, revoked_at
                FROM api_keys
                WHERE key_hash = ?
                """,
                (self._hash(plaintext),),
            ).fetchone()
        if row is None:
            return APIKeyValidation("invalid")
        key_id, label, expires_raw, revoked_at = row
        expires_at = self._parse(expires_raw)
        if revoked_at is not None:
            return APIKeyValidation("revoked", key_id, label, expires_at)
        if datetime.now(UTC) >= expires_at:
            return APIKeyValidation("expired", key_id, label, expires_at)
        return APIKeyValidation("active", key_id, label, expires_at)

    def renew(self, key_id: str, days: int = 365) -> datetime:
        if days < 1:
            raise ValueError("days must be positive")
        if not self.ready():
            raise KeyError(key_id)
        now = datetime.now(UTC)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT expires_at FROM api_keys WHERE id = ?",
                (key_id,),
            ).fetchone()
            if row is None:
                raise KeyError(key_id)
            current_expiry = self._parse(row[0])
            new_expiry = max(now, current_expiry) + timedelta(days=days)
            connection.execute(
                "UPDATE api_keys SET expires_at = ?, revoked_at = NULL WHERE id = ?",
                (self._format(new_expiry), key_id),
            )
        return new_expiry

    def revoke(self, key_id: str) -> None:
        if not self.ready():
            raise KeyError(key_id)
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE api_keys SET revoked_at = ? WHERE id = ?",
                (self._format(datetime.now(UTC)), key_id),
            )
        if cursor.rowcount != 1:
            raise KeyError(key_id)

    def list_keys(self) -> list[dict[str, str | None]]:
        if not self.ready():
            return []
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, label, key_prefix, created_at, expires_at, revoked_at
                FROM api_keys
                ORDER BY created_at
                """
            ).fetchall()
        return [
            {
                "id": row[0],
                "label": row[1],
                "key_prefix": row[2],
                "created_at": row[3],
                "expires_at": row[4],
                "revoked_at": row[5],
            }
            for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database, timeout=5)

    @staticmethod
    def _hash(plaintext: str) -> str:
        return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()

    @staticmethod
    def _format(value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _parse(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
