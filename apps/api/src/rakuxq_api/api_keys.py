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
        if os.name != "nt":
            self.database.chmod(0o600)

    def create(self, label: str, days: int = 365) -> tuple[str, str, datetime]:
        if not label.strip():
            raise ValueError("label must not be empty")
        if days < 1:
            raise ValueError("days must be positive")
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
        return key_id, plaintext, expires_at

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
