"""Versioned legal documents and a separate, minimal acceptance ledger.

No image/FEN collection, model training, identity registration or API-key mutation.
"""

from __future__ import annotations

import hashlib
import html
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

VERSION = "1.0"
EFFECTIVE_DATE = "2026-10-21"
COOKIE_NAME = "rakuxq_legal_receipt"
RECEIPT_SECONDS = 3 * 365 * 24 * 3600
TRAINING_COLLECTION_ENABLED = False
DOCUMENT_ROOT = Path(__file__).with_name("static") / "legal" / VERSION
DOCUMENTS = {
    name: (DOCUMENT_ROOT / f"{name}.txt").read_text(encoding="utf-8")
    for name in ("terms", "privacy")
}
HASHES = {
    name: hashlib.sha256(value.encode("utf-8")).hexdigest() for name, value in DOCUMENTS.items()
}


def metadata() -> dict[str, object]:
    return {
        "version": VERSION,
        "effective_date": EFFECTIVE_DATE,
        "terms_sha256": HASHES["terms"],
        "privacy_sha256": HASHES["privacy"],
        "terms_url": "/terms",
        "privacy_url": "/privacy",
        "training_collection_enabled": TRAINING_COLLECTION_ENABLED,
        "original_retention_hours": 12,
        "training_sample_max_years": 3,
        "acceptance_record_max_years": 3,
    }


def document_html(name: str) -> str:
    text = DOCUMENTS[name]
    lines = text.splitlines()
    title = html.escape(lines[0])
    paragraphs = []
    for line in lines[1:]:
        if not line.strip():
            continue
        escaped = html.escape(line)
        if line.startswith("第") and "条" in line[:8]:
            paragraphs.append(f"<h2>{escaped}</h2>")
        elif line.startswith("【"):
            paragraphs.append(f'<p class="legal-important">{escaped}</p>')
        else:
            paragraphs.append(f"<p>{escaped}</p>")
    shell = (
        Path(__file__)
        .with_name("static")
        .joinpath("legal-shell.html")
        .read_text(
            encoding="utf-8",
        )
    )
    return (
        shell.replace("{{TITLE}}", title)
        .replace("{{BODY}}", "\n".join(paragraphs))
        .replace("{{NAME}}", name)
        .replace("{{VERSION}}", VERSION)
        .replace("{{HASH}}", HASHES[name])
    )


class ConsentStore:
    """Opaque receipt hashes only; no raw IP, cookie, image, FEN or API key."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS legal_acceptances (
                receipt_hash TEXT PRIMARY KEY, key_reference TEXT,
                version TEXT NOT NULL, terms_hash TEXT NOT NULL,
                privacy_hash TEXT NOT NULL, accepted_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            )""")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS legal_expiry ON legal_acceptances(expires_at)"
            )
        self.path.chmod(0o600)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=3)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def prune(self, now: datetime | None = None) -> int:
        timestamp = int((now or datetime.now(UTC)).timestamp())
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM legal_acceptances WHERE expires_at <= ?",
                (timestamp,),
            )
        return cursor.rowcount

    def accepted(self, token: str | None, now: datetime | None = None) -> bool:
        if not token or len(token) > 128:
            return False
        timestamp = int((now or datetime.now(UTC)).timestamp())
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM legal_acceptances WHERE receipt_hash=? AND version=? "
                "AND terms_hash=? AND privacy_hash=? AND expires_at>?",
                (self._digest(token), VERSION, HASHES["terms"], HASHES["privacy"], timestamp),
            ).fetchone()
        return row is not None

    def accept(self, key_id: str | None = None, now: datetime | None = None) -> str:
        current = now or datetime.now(UTC)
        self.prune(current)
        token = secrets.token_urlsafe(32)
        key_reference = self._digest("rakuxq-legal:" + key_id) if key_id else None
        with self._connect() as connection:
            # Never evict unexpired legal evidence to make room for anonymous spam.
            count = connection.execute("SELECT count(*) FROM legal_acceptances").fetchone()[0]
            if count >= 100_000:
                raise ValueError("Acceptance ledger capacity reached")
            connection.execute(
                "INSERT INTO legal_acceptances VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    self._digest(token),
                    key_reference,
                    VERSION,
                    HASHES["terms"],
                    HASHES["privacy"],
                    int(current.timestamp()),
                    int((current + timedelta(seconds=RECEIPT_SECONDS)).timestamp()),
                ),
            )
        return token
