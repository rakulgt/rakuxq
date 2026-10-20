import hashlib
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from rakuxq_api import main
from rakuxq_api.api_keys import APIKeyValidation
from rakuxq_api.legal import COOKIE_NAME, DOCUMENTS, HASHES, VERSION, ConsentStore


@pytest.fixture
def legal_client(tmp_path, monkeypatch):
    store = ConsentStore(tmp_path / "legal.sqlite3")
    monkeypatch.setattr(main, "legal_store", store)
    monkeypatch.setattr(main, "settings", replace(main.settings, require_api_key=False))
    client = TestClient(main.app)
    yield client, store
    client.close()


def acceptance():
    return {
        "version": VERSION,
        "terms_sha256": HASHES["terms"],
        "privacy_sha256": HASHES["privacy"],
        "accepted": True,
        "training_license": True,
    }


def test_reading_is_not_acceptance(legal_client):
    client, store = legal_client
    for path in ("/terms", "/privacy", "/legal/versions", "/legal/1.0/terms", "/legal/1.0/privacy"):
        response = client.get(path)
        assert response.status_code == 200
        assert "RakuXQ" in response.text
        assert "Set-Cookie" not in response.headers
    status = client.get("/api/legal/status").json()
    assert status["accepted"] is False
    assert status["training_collection_enabled"] is False
    assert status["training_sample_max_years"] == 3
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT count(*) FROM legal_acceptances").fetchone()[0] == 0


@pytest.mark.parametrize("name", ["terms", "privacy"])
def test_archive_hash_and_final_text(legal_client, name):
    client, _ = legal_client
    response = client.get(f"/legal/1.0/{name}.txt")
    assert response.text == DOCUMENTS[name]
    assert hashlib.sha256(response.content).hexdigest() == HASHES[name]
    assert "审批稿" not in response.text and "【正式发布" not in response.text
    assert "北京市房山区长阳镇燕保大学城家园东区8号楼" in response.text
    assert "2026年10月21日" in response.text
    assert client.get("/legal/1.0/unknown.txt").status_code == 404


def test_confirmation_is_private_and_idempotent(legal_client):
    client, store = legal_client
    response = client.post(
        "/api/legal/acceptances", json=acceptance(), headers={"Origin": "http://testserver"}
    )
    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/legal/status").json()["accepted"] is True
    token = client.cookies.get(COOKIE_NAME)
    assert token not in response.text
    client.post(
        "/api/legal/acceptances", json=acceptance(), headers={"Origin": "http://testserver"}
    )
    with sqlite3.connect(store.path) as connection:
        rows = connection.execute("SELECT * FROM legal_acceptances").fetchall()
        names = {row[1] for row in connection.execute("PRAGMA table_info(legal_acceptances)")}
    assert len(rows) == 1 and token not in str(rows)
    assert not names.intersection({"ip", "image", "fen", "api_key", "user_agent", "cookie"})


@pytest.mark.parametrize(
    "field,value",
    [("accepted", False), ("training_license", False), ("accepted", "true"), ("accepted", 1)],
)
def test_explicit_true_required(legal_client, field, value):
    client, _ = legal_client
    payload = acceptance()
    payload[field] = value
    assert (
        client.post(
            "/api/legal/acceptances", json=payload, headers={"Origin": "http://testserver"}
        ).status_code
        == 422
    )
    assert client.get("/api/legal/status").json()["accepted"] is False


@pytest.mark.parametrize("field", ["version", "terms_sha256", "privacy_sha256"])
def test_stale_or_tampered_document_rejected(legal_client, field):
    client, _ = legal_client
    payload = acceptance()
    payload[field] = "old-or-tampered"
    assert (
        client.post(
            "/api/legal/acceptances", json=payload, headers={"Origin": "http://testserver"}
        ).status_code
        == 409
    )


@pytest.mark.parametrize("origin", [None, "https://evil.example", "https://testserver"])
def test_same_origin_required(legal_client, origin):
    client, _ = legal_client
    headers = {"Origin": origin} if origin else {}
    assert (
        client.post("/api/legal/acceptances", json=acceptance(), headers=headers).status_code == 403
    )


def test_forged_cookie_rejected(legal_client):
    client, _ = legal_client
    client.cookies.set(COOKIE_NAME, "pretend-accepted")
    assert client.get("/api/legal/status").json()["accepted"] is False


def test_secure_hosted_cookie(legal_client, monkeypatch):
    client, _ = legal_client
    monkeypatch.setattr(main, "settings", replace(main.settings, require_api_key=True))
    response = client.post(
        "/api/legal/acceptances", json=acceptance(), headers={"Origin": "http://testserver"}
    )
    assert "Secure" in response.headers["set-cookie"]


def test_expiry_and_cleanup(tmp_path):
    store = ConsentStore(tmp_path / "proof.sqlite3")
    now = datetime(2026, 10, 21, tzinfo=UTC)
    token = store.accept(now=now)
    assert store.accepted(token, now + timedelta(days=1094))
    assert not store.accepted(token, now + timedelta(days=1095))
    assert store.prune(now + timedelta(days=1095)) == 1
    assert store.prune(now + timedelta(days=1096)) == 0


def test_unavailable_ledger_does_not_report_success(legal_client, monkeypatch):
    client, _ = legal_client
    monkeypatch.setattr(main, "legal_store", None)
    assert (
        client.post(
            "/api/legal/acceptances", json=acceptance(), headers={"Origin": "http://testserver"}
        ).status_code
        == 503
    )


def test_key_confirmation_does_not_change_permissions(legal_client):
    client, store = legal_client
    key_id = "test-key-id-not-a-secret"
    main.app.dependency_overrides[main.require_api_key] = lambda: APIKeyValidation(
        "active",
        key_id=key_id,
        label="test",
    )
    try:
        response = client.post("/v1/legal/acceptance", json=acceptance())
    finally:
        main.app.dependency_overrides.pop(main.require_api_key, None)
    assert response.status_code == 200
    with sqlite3.connect(store.path) as connection:
        reference = connection.execute("SELECT key_reference FROM legal_acceptances").fetchone()[0]
    assert reference and reference != key_id
    assert key_id not in response.text
    assert response.json()["training_collection_enabled"] is False


def test_public_text_does_not_contain_internal_protocols():
    for text in DOCUMENTS.values():
        assert "RakuLAW" not in text and "D:/" not in text and "/opt/raku" not in text
        assert "12小时" in text and "3年" in text
    assert "仅浏览网页" in DOCUMENTS["terms"]
