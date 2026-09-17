from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from rakuxq_api.api_keys import APIKeyStore
from rakuxq_api.config import Settings
from rakuxq_api.domain import BoardPrediction, CellPrediction, Orientation
from rakuxq_api.main import app
from rakuxq_api.providers.base import RecognitionProvider
from rakuxq_api.service import RecognitionService

START_GRID = [
    list("rnbakabnr"),
    list("........."),
    list(".c.....c."),
    list("p.p.p.p.p"),
    list("........."),
    list("........."),
    list("P.P.P.P.P"),
    list(".C.....C."),
    list("........."),
    list("RNBAKABNR"),
]


class AuthTestProvider(RecognitionProvider):
    name = "auth-test"

    def ready(self):
        return True

    def recognize(self, image, orientation):
        cells = [
            CellPrediction(rank, file, symbol, 0.999)
            for rank, row in enumerate(START_GRID)
            for file, symbol in enumerate(row)
        ]
        return BoardPrediction(
            grid=[row.copy() for row in START_GRID],
            cells=cells,
            orientation=Orientation.RED_BOTTOM,
            board_confidence=0.999,
            provider=self.name,
            model_version="test",
        )


def test_api_key_store_create_validate_renew_and_revoke(tmp_path):
    store = APIKeyStore(tmp_path / "keys.sqlite3")
    key_id, plaintext, first_expiry = store.create("customer-a", days=30)

    active = store.validate(plaintext)
    assert active.status == "active"
    assert active.key_id == key_id
    assert active.label == "customer-a"
    assert store.validate("wrong-key").status == "invalid"

    renewed_expiry = store.renew(key_id, days=365)
    assert renewed_expiry > first_expiry + timedelta(days=364)
    store.revoke(key_id)
    assert store.validate(plaintext).status == "revoked"


def test_expired_api_key_returns_renewal_json(tmp_path):
    database = tmp_path / "keys.sqlite3"
    store = APIKeyStore(database)
    _, plaintext, _ = store.create("expired-customer")
    expired_at = (datetime.now(UTC) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE api_keys SET expires_at = ?", (expired_at,))

    protected_settings = replace(
        Settings(),
        require_api_key=True,
        api_keys_db=str(database),
    )
    client = TestClient(app)
    with (
        patch("rakuxq_api.main.settings", protected_settings),
        patch("rakuxq_api.main.api_key_store", store),
    ):
        response = client.post(
            "/v1/recognitions",
            headers={"Authorization": f"Bearer {plaintext}"},
            files={"image": ("board.png", b"image", "image/png")},
            data={"side_to_move": "red"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == {
        "code": "API_KEY_EXPIRED",
        "message": "API key expired. Contact WeChat lgtqcn to renew.",
        "renewal": {"wechat": "lgtqcn", "price_cny": 39, "period_days": 365},
    }


def test_valid_api_key_allows_json_recognition(tmp_path):
    database = tmp_path / "keys.sqlite3"
    store = APIKeyStore(database)
    _, plaintext, _ = store.create("customer-a")
    protected_settings = replace(
        Settings(),
        require_api_key=True,
        api_keys_db=str(database),
    )
    fake_service = RecognitionService(AuthTestProvider())
    client = TestClient(app)

    with (
        patch("rakuxq_api.main.settings", protected_settings),
        patch("rakuxq_api.main.api_key_store", store),
        patch("rakuxq_api.main.service", fake_service),
    ):
        missing = client.post(
            "/v1/recognitions",
            files={"image": ("board.png", b"image", "image/png")},
            data={"side_to_move": "red"},
        )
        accepted = client.post(
            "/v1/recognitions",
            headers={"X-API-Key": plaintext},
            files={"image": ("board.png", b"image", "image/png")},
            data={"side_to_move": "red"},
        )

    assert missing.status_code == 401
    assert missing.json()["detail"]["code"] == "API_KEY_REQUIRED"
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["fen"].endswith(" w - - 0 1")
