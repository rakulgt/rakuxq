# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Li Guotai
# Artifact-ID: rakuxq.native.b-trial-tests
# Role: Fixed deadline, authentication, isolation and concurrency regression checks.
# Inputs: Synthetic requests and fake app/clock. Outputs: assertions without production access.
# Provenance: Project-authored, AI-assisted. State: experimental trial guards only.
from __future__ import annotations

import asyncio
import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

SPEC = importlib.util.spec_from_file_location(
    "rakuxq_b_trial", Path(__file__).resolve().parents[1] / "tools/serve_b.py"
)
trial = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(trial)
NOW = datetime(2026, 10, 21, tzinfo=UTC)


def test_absolute_deadline_cannot_be_reset_by_restarting():
    expiry = NOW + timedelta(hours=48)
    assert trial.deadline_from(expiry.isoformat(), NOW) == expiry
    assert trial.deadline_from(expiry.isoformat(), NOW + timedelta(hours=47)) == expiry
    for value in (NOW.isoformat(), (expiry + timedelta(seconds=1)).isoformat(), "2026-10-22"):
        with pytest.raises(ValueError):
            trial.deadline_from(value, NOW)
    with pytest.raises(ValueError):
        trial.deadline_from(expiry.isoformat(), expiry)


def test_trial_preserves_body_and_tags_responses_without_a_fallback():
    app = FastAPI()
    app.post("/v1/solutions")(lambda: {"status": "accepted", "best_move": {"notation": "车一进一"}})

    def authorize(headers):
        if headers.get("x-api-key") != "synthetic-test-only":
            raise HTTPException(401, {"code": "API_KEY_REQUIRED"})

    window = trial.TrialWindow(app, NOW + timedelta(hours=48), authorize, lambda: NOW)
    with TestClient(window) as client:
        assert client.post("/v1/solutions").status_code == 401
        response = client.post("/v1/solutions", headers={"X-API-Key": "synthetic-test-only"})
        assert response.json()["status"] == "accepted"
        assert response.json()["best_move"]["notation"] == "车一进一"
        assert response.headers["x-rakuxq-plan"] == "B-experimental"
        assert response.headers["cache-control"] == "no-store"
        assert client.post("/api/public/trial-keys").status_code == 404
        assert client.post("/api/lab/analyses").status_code == 404
        assert client.get("/v1/solutions").status_code == 405
        window.clock = lambda: NOW + timedelta(hours=48)
        expired = client.post("/v1/solutions", headers={"X-API-Key": "synthetic-test-only"})
        assert expired.status_code == 410
        assert expired.json()["detail"]["code"] == "B_TEST_EXPIRED"


def test_only_one_b_request_is_active_at_a_time():
    async def scenario():
        app = FastAPI()
        entered, release = asyncio.Event(), asyncio.Event()

        @app.post("/v1/solutions")
        async def solve():
            entered.set()
            await release.wait()
            return {"status": "accepted"}

        window = trial.TrialWindow(app, NOW + timedelta(hours=48), lambda _: None, lambda: NOW)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=window), base_url="http://test"
        ) as client:
            first = asyncio.create_task(client.post("/v1/solutions"))
            await asyncio.wait_for(entered.wait(), 3)
            try:
                assert (await client.post("/v1/solutions")).status_code == 429
            finally:
                release.set()
                assert (await first).status_code == 200
            assert (await client.post("/v1/solutions")).status_code == 200

    asyncio.run(scenario())
