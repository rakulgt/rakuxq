"""Reserve/settle optional hosted API quotas; no change to engine permissions.

Copyright 2026 Li Guotai. MIT. Original RakuXQ API accounting implementation.
Only successful business results spend credit, not HTTP 200 alone. A process crash
leaves its reservation held for operator reconciliation; never expire it blindly
while work may still finish. Settlement is not proof of client-side delivery.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .api_keys import APIKeyQuotaUnavailable, APIKeyStore

METERED_PATHS = {"/v1/recognitions", "/v1/fen", "/v1/analyses", "/v1/solutions", "/v1/solve"}


def chargeable(path: str, status: int, body: bytes) -> bool:
    if status != 200:
        return False
    if path == "/v1/fen":
        return bool(body.strip())
    try:
        data = json.loads(body)
    except (ValueError, UnicodeError):
        return False
    if not isinstance(data, dict):
        return False
    if path == "/v1/recognitions":
        return data.get("status") == "accepted" and bool(data.get("fen"))
    if path == "/v1/solve":
        analysis = data.get("analysis")
        return (data.get("status") == "accepted" and isinstance(analysis, dict)
                and analysis.get("status") == "completed" and bool(analysis.get("best_move")))
    state = data.get("analysis_status") if path == "/v1/solutions" else data.get("status")
    return state == "completed" and bool(data.get("best_move"))


def quota_headers(quota: dict[str, int]) -> dict[str, str]:
    return {f"X-RakuXQ-Quota-{name.replace('_', '-')}": str(value)
            for name, value in quota.items()}


class APIKeyQuotaMiddleware:
    def __init__(self, app: ASGIApp, store_getter: Callable[[], APIKeyStore | None],
                 enabled: Callable[[], bool]):
        self.app, self.store_getter, self.enabled = app, store_getter, enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (scope["type"] != "http" or scope.get("method") != "POST"
                or scope.get("path") not in METERED_PATHS or not self.enabled()):
            await self.app(scope, receive, send)
            return
        store = self.store_getter()
        if store is None:
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        supplied = headers.get("x-api-key")
        authorization = headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            supplied = authorization[7:].strip()
        validation = store.validate(supplied)
        if validation.status != "active" or validation.key_id is None:
            await self.app(scope, receive, send)
            return
        key_id = validation.key_id
        try:
            reservation = store.reserve_usage(key_id)
        except APIKeyQuotaUnavailable as exc:
            busy = exc.quota["in_flight"] > 0
            response = JSONResponse(
                {"detail": {"code": "API_KEY_QUOTA_BUSY" if busy else "API_KEY_QUOTA_EXHAUSTED",
                            "message": "Credits are reserved by active requests." if busy
                            else "Usage quota exhausted.", "quota": exc.quota}},
                status_code=429,
                headers={**quota_headers(exc.quota), "Cache-Control": "no-store",
                         **({"Retry-After": "1"} if busy else {})},
            )
            await response(scope, receive, send)
            return
        except sqlite3.Error:
            await JSONResponse({"detail": {"code": "API_QUOTA_UNAVAILABLE"}}, 503)(
                scope, receive, send,
            )
            return
        if reservation is None:
            await self.app(scope, receive, send)
            return
        messages: list[Message] = []
        size = 0

        async def collect(message: Message) -> None:
            nonlocal size
            size += len(message.get("body", b""))
            if size > 1024 * 1024:
                raise RuntimeError("Metered response exceeds safe accounting buffer")
            messages.append(message)

        settled = False
        try:
            await self.app(scope, receive, collect)
            start = next(m for m in messages if m["type"] == "http.response.start")
            body = b"".join(m.get("body", b"") for m in messages)
            quota = store.finish_usage(
                key_id, reservation, chargeable(scope["path"], start["status"], body),
            )
            settled = True
            start["headers"] = [*start.get("headers", []), *[
                (name.lower().encode("ascii"), value.encode("ascii"))
                for name, value in quota_headers(quota).items()
            ], (b"cache-control", b"no-store")]
            for message in messages:
                await send(message)
        finally:
            if not settled:
                store.finish_usage(key_id, reservation, False)
