from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from rakuxq_api.api_keys import APIKeyStore
from rakuxq_api.audit import AUDITED_PATHS, InteractionAuditMiddleware, InteractionAuditStore
from rakuxq_api.domain import BoardPrediction, CellPrediction, Orientation
from rakuxq_api.main import app
from rakuxq_api.providers.base import RecognitionProvider
from rakuxq_api.service import RecognitionService


class AuditProvider(RecognitionProvider):
    name = "audit-test"

    def ready(self):
        return True

    def recognize(self, image, orientation):
        grid = [list(".........") for _ in range(10)]
        grid[0][4] = "k"
        grid[5][4] = "p"
        grid[9][4] = "K"
        cells = [
            CellPrediction(rank, file, grid[rank][file], 0.999)
            for rank in range(10)
            for file in range(9)
        ]
        return BoardPrediction(
            grid=grid,
            cells=cells,
            orientation=Orientation.RED_BOTTOM,
            board_confidence=0.999,
            provider=self.name,
            model_version="test",
        )


client = TestClient(app)


def _records(root: Path) -> list[Path]:
    return sorted(item for item in root.iterdir() if item.is_dir())


def test_audit_preserves_original_upload_and_response_for_twelve_hours(tmp_path):
    store = InteractionAuditStore(tmp_path, retention_hours=12, max_total_bytes=10_000_000)
    fake_service = RecognitionService(AuditProvider())
    original = b"original-image-payload"

    with (
        patch("rakuxq_api.main.audit_store", store),
        patch("rakuxq_api.main.service", fake_service),
    ):
        response = client.post(
            "/v1/recognitions",
            files={"image": ("board.png", original, "image/png")},
            data={"side_to_move": "red", "orientation": "auto"},
        )

    assert response.status_code == 200
    record = _records(tmp_path)[0]
    assert (record / "image.png").read_bytes() == original
    assert json.loads((record / "response.json").read_text("utf-8"))["status"] == "accepted"
    metadata = json.loads((record / "interaction.json").read_text("utf-8"))
    assert metadata["retention_hours"] == 12
    assert metadata["request"]["fields"]["side_to_move"] == "red"
    assert metadata["request"]["uploads"][0]["sha256"]
    assert metadata["response"]["http_status"] == 200
    assert metadata["response"]["recognition_status"] == "accepted"
    assert "authorization" not in json.dumps(metadata).lower()


def test_audit_records_validation_failure_when_no_image_arrives(tmp_path):
    store = InteractionAuditStore(tmp_path, retention_hours=12, max_total_bytes=10_000_000)

    with patch("rakuxq_api.main.audit_store", store):
        response = client.post(
            "/v1/recognitions",
            data={"side_to_move": "red", "orientation": "auto"},
        )

    assert response.status_code == 422
    record = _records(tmp_path)[0]
    metadata = json.loads((record / "interaction.json").read_text("utf-8"))
    assert metadata["request"]["uploads"] == []
    assert metadata["response"]["http_status"] == 422
    assert "Field required" in (record / "response.json").read_text("utf-8")


def test_audit_prunes_expired_records(tmp_path):
    store = InteractionAuditStore(tmp_path, retention_hours=12, max_total_bytes=10_000_000)
    expired = tmp_path / "expired"
    current = tmp_path / "current"
    expired.mkdir()
    current.mkdir()
    old = (datetime.now(UTC) - timedelta(hours=13)).timestamp()
    os.utime(expired, (old, old))

    removed = store.prune()

    assert removed == 1
    assert not expired.exists()
    assert current.exists()


def test_solve_uploads_are_audited_and_nested_recognition_fields_are_visible():
    assert "/v1/solve" in AUDITED_PATHS
    payload = {"recognition": {"request_id": "rec_nested", "full_fen": "4k4/9 w"}}
    assert InteractionAuditStore._nested(payload, "request_id") == "rec_nested"
    assert InteractionAuditStore._nested(payload, "full_fen") == "4k4/9 w"


def test_secured_audit_keeps_only_active_key_requests(tmp_path):
    audit_store = InteractionAuditStore(
        tmp_path / "audits", retention_hours=12, max_total_bytes=10_000_000
    )
    key_store = APIKeyStore(tmp_path / "keys.sqlite3")
    key_id, plaintext, _expires_at = key_store.create("audit-test")
    secured = FastAPI()

    @secured.post("/v1/recognitions")
    async def consume_body(request: Request):
        await request.body()
        return {"status": "accepted"}

    secured.add_middleware(
        InteractionAuditMiddleware,
        store_getter=lambda: audit_store,
        key_store_getter=lambda: key_store,
        require_api_key=True,
        max_request_bytes=1_000_000,
    )
    secured_client = TestClient(secured)
    upload = {"image": ("board.png", b"authenticated-image", "image/png")}

    assert secured_client.post("/v1/recognitions", files=upload).status_code == 200
    assert not (tmp_path / "audits").exists()

    response = secured_client.post(
        "/v1/recognitions",
        files=upload,
        headers={"Authorization": f"Bearer {plaintext}"},
    )

    assert response.status_code == 200
    record = _records(tmp_path / "audits")[0]
    metadata = json.loads((record / "interaction.json").read_text("utf-8"))
    assert metadata["request"]["key_id"] == key_id
    assert (record / "image.png").read_bytes() == b"authenticated-image"
