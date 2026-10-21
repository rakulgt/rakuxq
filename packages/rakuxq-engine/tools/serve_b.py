#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Li Guotai
# Artifact-ID: rakuxq.native.b-trial
# Role: Fixed-expiry, authenticated isolated online B experiment; never select production A.
# Inputs: Pinned own executable/model, existing API settings, absolute UTC deadline.
# Outputs: Compatible v1 responses with B/expiry headers. Provenance: Project-authored, AI-assisted.
# State: experimental, explicitly authorized 48-hour trial; not production promotion.
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

PUBLIC_PATHS = {"/v1/recognitions", "/v1/fen", "/v1/solve", "/v1/solutions", "/v1/analyses"}


def deadline_from(value: str, now: datetime | None = None) -> datetime:
    deadline = datetime.fromisoformat(value.replace("Z", "+00:00"))
    current = now or datetime.now(UTC)
    if deadline.tzinfo is None or not current < deadline <= current + timedelta(hours=48):
        raise ValueError("B requires an unexpired absolute deadline no more than 48 hours away")
    return deadline.astimezone(UTC)


class TrialWindow:
    def __init__(self, app, deadline: datetime, authorize: Callable, clock=None):
        self.app, self.deadline, self.authorize = app, deadline, authorize
        self.clock = clock or (lambda: datetime.now(UTC))
        self.busy = asyncio.Lock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def tagged(message):
            if message["type"] == "http.response.start":
                headers = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower()
                    not in {b"cache-control", b"x-rakuxq-plan", b"x-rakuxq-test-expires-at"}
                ]
                message = {
                    **message,
                    "headers": headers
                    + [
                        (b"cache-control", b"no-store"),
                        (b"x-rakuxq-plan", b"B-experimental"),
                        (b"x-rakuxq-test-expires-at", self.deadline.isoformat().encode("ascii")),
                    ],
                }
            await send(message)

        async def error(status, code, text, headers=None):
            response = JSONResponse(
                {"detail": {"code": code, "message": text}}, status_code=status, headers=headers
            )
            await response(scope, receive, tagged)

        if self.clock() >= self.deadline:
            return await error(410, "B_TEST_EXPIRED", "B test window has expired; A is unchanged.")
        path = scope["path"]
        if path == "/healthz" and scope["method"] in {"GET", "HEAD"}:
            return await self.app(scope, receive, tagged)
        if path not in PUBLIC_PATHS:
            return await error(
                404, "B_PATH_NOT_AVAILABLE", "Only the existing v1 APIs are enabled."
            )
        if scope["method"] != "POST":
            return await error(405, "METHOD_NOT_ALLOWED", "Use POST.", {"Allow": "POST"})
        try:
            await run_in_threadpool(self.authorize, Headers(scope=scope))
        except HTTPException as exc:
            return await JSONResponse(
                {"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers
            )(scope, receive, tagged)
        if self.busy.locked():
            return await error(
                429, "B_TEST_BUSY", "B processes one request at a time.", {"Retry-After": "1"}
            )
        async with self.busy:
            return await self.app(scope, receive, tagged)


def create_app():
    deadline = deadline_from(os.environ["RAKUXQ_B_EXPIRES_AT"])
    for setting in ("RAKUXQ_ENGINE_PATH", "RAKUXQ_ENGINE_NETWORK"):
        path = Path(os.environ[setting])
        expected = os.environ[setting + "_SHA256"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("B executable/model fingerprint changed")
    from pipeline import validate_own_model

    network = Path(os.environ["RAKUXQ_ENGINE_NETWORK"])
    receipt = json.loads(network.with_suffix(network.suffix + ".meta.json").read_text())
    validate_own_model(receipt, os.environ["RAKUXQ_ENGINE_NETWORK_SHA256"])
    if os.environ.get("RAKUXQ_PUBLIC_METRICS_DB"):
        raise ValueError("B must not publish experiments in A metrics")

    from rakuxq_api import main

    if not main.settings.require_api_key or not main.settings.engine_allowed_key_ids:
        raise ValueError("B requires the existing private engine key allowlist")
    if main.settings.engine_threads != 1 or main.settings.ort_intra_op_threads != 1:
        raise ValueError("B must remain single-thread limited")

    def authorize(headers):
        validation = main.require_api_key(
            authorization=headers.get("authorization"), x_api_key=headers.get("x-api-key")
        )
        main.require_engine_api_key(validation)

    return TrialWindow(main.app, deadline, authorize)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--prune-audit", action="store_true", required=True)
    args = parser.parse_args()
    from rakuxq_api.audit import InteractionAuditStore

    audit_root = Path("/opt/raku/logs/rakuxq/b-interactions")
    if audit_root.resolve() != audit_root:
        raise ValueError("Unexpected B audit root")
    print(f"Pruned {InteractionAuditStore(audit_root, 12, 256 * 1024 * 1024).prune()} B audits")
