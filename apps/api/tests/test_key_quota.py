"""Quota contracts, concurrency and HTTP settlement; no real customer keys."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from rakuxq_api.api_keys import APIKeyQuotaUnavailable, APIKeyStore
from rakuxq_api.config import Settings
from rakuxq_api.key_quota import APIKeyQuotaMiddleware, chargeable
from rakuxq_api.main import app


def test_500_credit_boundary_and_unlimited_old_keys(tmp_path):
    store = APIKeyStore(tmp_path / "keys.sqlite3")
    key_id, _, _ = store.create("personal", uses=500)
    unlimited, _, _ = store.create("existing")
    assert store.reserve_usage(unlimited) is None
    for n in range(500):
        reservation = store.reserve_usage(key_id)
        assert reservation
        assert store.finish_usage(key_id, reservation, True)["used"] == n + 1
    assert store.quota(key_id) == {"limit": 500, "used": 500, "in_flight": 0, "remaining": 0}
    with pytest.raises(APIKeyQuotaUnavailable):
        store.reserve_usage(key_id)
    assert APIKeyStore(store.database).quota(key_id)["used"] == 500


def test_atomic_reservations_failure_refund_and_double_settlement(tmp_path):
    store = APIKeyStore(tmp_path / "keys.sqlite3")
    key_id, _, _ = store.create("concurrent", uses=7)

    def reserve(_):
        try:
            return APIKeyStore(store.database).reserve_usage(key_id)
        except APIKeyQuotaUnavailable:
            return None

    with ThreadPoolExecutor(max_workers=16) as pool:
        held = [value for value in pool.map(reserve, range(40)) if value]
    assert len(held) == 7
    assert store.quota(key_id)["remaining"] == 0
    store.finish_usage(key_id, held[0], False)
    replacement = store.reserve_usage(key_id)
    for reservation in [*held[1:], replacement]:
        store.finish_usage(key_id, reservation, True)
    assert store.quota(key_id)["used"] == 7
    with pytest.raises(ValueError):
        store.finish_usage(key_id, replacement, True)


@pytest.mark.parametrize("uses", [0, -1, True, 1.5])
def test_invalid_quota_does_not_create_key(tmp_path, uses):
    store = APIKeyStore(tmp_path / "keys.sqlite3")
    with pytest.raises(ValueError):
        store.create("bad", uses=uses)
    assert store.list_keys() == []


@pytest.mark.parametrize("path,data,expected", [
    ("/v1/recognitions", {"status": "accepted", "fen": "fen"}, True),
    ("/v1/recognitions", {"status": "review_required", "fen": "fen"}, False),
    ("/v1/analyses", {"status": "completed", "best_move": {"iccs": "a0a1"}}, True),
    ("/v1/solutions", {"status": "accepted", "analysis_status": "completed",
                       "best_move": {"iccs": "a0a1"}}, True),
    ("/v1/solve", {"status": "accepted", "analysis": {
        "status": "completed", "best_move": {"iccs": "a0a1"}}}, True),
    ("/v1/solve", {"status": "partial_success", "analysis": None}, False),
    ("/v1/solve", {"status": "accepted", "analysis": {"status": "terminal"}}, False),
])
def test_business_success_not_http_200(path, data, expected):
    import json
    assert chargeable(path, 200, json.dumps(data).encode()) is expected
    assert chargeable(path, 503, json.dumps(data).encode()) is False


def test_middleware_refunds_errors_and_counts_fusion_once(tmp_path):
    store = APIKeyStore(tmp_path / "keys.sqlite3")
    key_id, plaintext, _ = store.create("personal", uses=2)
    replies = [({"status": "review_required"}, 200), ({"detail": "bad"}, 422),
               ({"status": "partial_success", "analysis": None}, 200),
               ({"status": "accepted", "analysis": {
                   "status": "completed", "best_move": {"iccs": "a0a1"}}}, 200)]

    async def route(request):
        payload, status = replies[0]
        return JSONResponse(payload, status_code=status)

    mini = Starlette(routes=[Route("/v1/solve", route, methods=["POST"])])
    mini.add_middleware(APIKeyQuotaMiddleware, store_getter=lambda: store, enabled=lambda: True)
    client = TestClient(mini)
    headers = {"Authorization": f"Bearer {plaintext}"}
    for _ in range(3):
        client.post("/v1/solve", headers=headers)
        replies.pop(0)
        assert store.quota(key_id)["remaining"] == 2
    first = client.post("/v1/solve", headers=headers)
    assert first.headers["x-rakuxq-quota-remaining"] == "1"
    assert client.post("/v1/solve", headers=headers).status_code == 200
    rejected = client.post("/v1/solve", headers=headers)
    assert rejected.status_code == 429
    assert rejected.json()["detail"]["code"] == "API_KEY_QUOTA_EXHAUSTED"
    assert store.quota(key_id)["used"] == 2


def test_quota_status_is_authenticated_and_not_charged(tmp_path):
    store = APIKeyStore(tmp_path / "keys.sqlite3")
    key_id, plaintext, _ = store.create("personal", uses=500)
    settings = replace(Settings(), require_api_key=True, api_keys_db=str(store.database))
    with patch("rakuxq_api.main.settings", settings), patch("rakuxq_api.main.api_key_store", store):
        client = TestClient(app)
        assert client.get("/v1/key-status").status_code == 401
        response = client.get("/v1/key-status", headers={"X-API-Key": plaintext})
        assert response.status_code == 200
        assert response.json()["quota"]["remaining"] == 500
        assert response.headers["cache-control"].startswith("no-store")
    assert store.quota(key_id)["used"] == 0


def test_application_exception_releases_reservation(tmp_path):
    store = APIKeyStore(tmp_path / "keys.sqlite3")
    key_id, plaintext, _ = store.create("personal", uses=1)

    async def route(request):
        raise RuntimeError("test failure before response")

    mini = Starlette(routes=[Route("/v1/solve", route, methods=["POST"])])
    mini.add_middleware(APIKeyQuotaMiddleware, store_getter=lambda: store, enabled=lambda: True)
    with pytest.raises(RuntimeError):
        TestClient(mini).post("/v1/solve", headers={"X-API-Key": plaintext})
    assert store.quota(key_id) == {"limit": 1, "used": 0, "in_flight": 0, "remaining": 1}


def test_cli_private_output_and_exclusive_replay(tmp_path):
    import json
    import subprocess
    import sys

    output, database = tmp_path / "private.json", tmp_path / "keys.sqlite3"
    command = [sys.executable, "-m", "rakuxq_api.key_cli", "--database", str(database),
               "create", "--label", "personal", "--uses", "500", "--output", str(output)]
    first = subprocess.run(command, capture_output=True, text=True)
    assert first.returncode == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["quota"]["remaining"] == 500
    assert payload["api_key"] not in first.stdout + first.stderr
    original = output.read_bytes()
    repeated = subprocess.run(command, capture_output=True, text=True)
    assert repeated.returncode != 0 and output.read_bytes() == original
    assert len(APIKeyStore(database).list_keys()) == 1
