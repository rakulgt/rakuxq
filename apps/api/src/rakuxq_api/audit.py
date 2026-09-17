from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .api_keys import APIKeyStore

LOGGER = logging.getLogger("rakuxq.audit")
AUDITED_PATHS = {"/v1/recognitions", "/v1/fen"}


@dataclass(slots=True)
class CapturedUpload:
    field: str
    filename: str | None
    content_type: str | None
    data: bytes


@dataclass(slots=True)
class ParsedRequest:
    fields: dict[str, str]
    uploads: list[CapturedUpload]
    parse_error: str | None = None


class InteractionAuditStore:
    def __init__(self, root: str | Path, retention_hours: int, max_total_bytes: int):
        self.root = Path(root)
        self.retention_hours = retention_hours
        self.max_total_bytes = max_total_bytes

    async def record(
        self,
        *,
        scope: Scope,
        request_body: bytes,
        request_truncated: bool,
        response_status: int,
        response_headers: list[tuple[bytes, bytes]],
        response_body: bytes,
        response_truncated: bool,
        duration_ms: int,
        key_id: str,
    ) -> None:
        parsed = await self._parse_request(scope, request_body, request_truncated)
        await asyncio.to_thread(
            self._persist,
            scope,
            parsed,
            request_body,
            request_truncated,
            response_status,
            response_headers,
            response_body,
            response_truncated,
            duration_ms,
            key_id,
        )

    def prune(self, now: datetime | None = None) -> int:
        if not self.root.exists():
            return 0
        cutoff = (now or datetime.now(UTC)).timestamp() - self.retention_hours * 3600
        removed = 0
        for entry in self.root.iterdir():
            if not entry.is_dir() or entry.stat().st_mtime > cutoff:
                continue
            shutil.rmtree(entry)
            removed += 1
        self._enforce_capacity()
        return removed

    async def _parse_request(
        self, scope: Scope, body: bytes, truncated: bool
    ) -> ParsedRequest:
        if truncated:
            return ParsedRequest({}, [], "request body exceeded audit capture limit")

        sent = False

        async def receive() -> Message:
            nonlocal sent
            if sent:
                return {"type": "http.request", "body": b"", "more_body": False}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(scope, receive)
        fields: dict[str, str] = {}
        uploads: list[CapturedUpload] = []
        try:
            async with request.form(max_files=4, max_fields=20) as form:
                for field, value in form.multi_items():
                    if isinstance(value, UploadFile):
                        uploads.append(
                            CapturedUpload(
                                field=field,
                                filename=value.filename,
                                content_type=value.content_type,
                                data=await value.read(),
                            )
                        )
                    else:
                        fields[field] = str(value)[:512]
        except Exception as exc:  # pragma: no cover - parser failures vary by Starlette
            return ParsedRequest(fields, uploads, f"{type(exc).__name__}: {exc}")
        return ParsedRequest(fields, uploads)

    def _persist(
        self,
        scope: Scope,
        parsed: ParsedRequest,
        request_body: bytes,
        request_truncated: bool,
        response_status: int,
        response_headers: list[tuple[bytes, bytes]],
        response_body: bytes,
        response_truncated: bool,
        duration_ms: int,
        key_id: str,
    ) -> None:
        now = datetime.now(UTC)
        audit_id = f"{now:%Y%m%dT%H%M%S.%fZ}_{uuid4().hex[:12]}"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        record_dir = self.root / audit_id
        record_dir.mkdir(mode=0o700)

        request_headers = Headers(scope=scope)
        response_header_map = Headers(raw=response_headers)
        upload_metadata: list[dict[str, Any]] = []
        for index, upload in enumerate(parsed.uploads, start=1):
            suffix = self._image_suffix(upload.content_type)
            image_name = "image" if upload.field == "image" and index == 1 else f"upload-{index}"
            image_path = record_dir / f"{image_name}{suffix}"
            self._write_private(image_path, upload.data)
            upload_metadata.append(
                {
                    "field": upload.field,
                    "filename": upload.filename,
                    "content_type": upload.content_type,
                    "size_bytes": len(upload.data),
                    "sha256": hashlib.sha256(upload.data).hexdigest(),
                    "stored_as": image_path.name,
                }
            )

        response_content_type = response_header_map.get("content-type", "")
        response_name = "response.json" if "json" in response_content_type else "response.txt"
        self._write_private(record_dir / response_name, response_body)

        parsed_response: dict[str, Any] | None = None
        if "json" in response_content_type and not response_truncated:
            try:
                candidate = json.loads(response_body)
                if isinstance(candidate, dict):
                    parsed_response = candidate
            except (UnicodeDecodeError, json.JSONDecodeError):
                parsed_response = None

        metadata = {
            "audit_id": audit_id,
            "received_at": now.isoformat().replace("+00:00", "Z"),
            "expires_at": (now + timedelta(hours=self.retention_hours))
            .isoformat()
            .replace("+00:00", "Z"),
            "retention_hours": self.retention_hours,
            "request": {
                "method": scope.get("method"),
                "path": scope.get("path"),
                "key_id": key_id,
                "content_type": request_headers.get("content-type"),
                "content_length": request_headers.get("content-length"),
                "captured_body_bytes": len(request_body),
                "body_truncated": request_truncated,
                "user_agent": request_headers.get("user-agent"),
                "cf_ray": request_headers.get("cf-ray"),
                "fields": parsed.fields,
                "uploads": upload_metadata,
                "parse_error": parsed.parse_error,
            },
            "response": {
                "http_status": response_status,
                "content_type": response_content_type,
                "size_bytes": len(response_body),
                "body_truncated": response_truncated,
                "stored_as": response_name,
                "request_id": self._nested(parsed_response, "request_id"),
                "recognition_status": self._nested(parsed_response, "status"),
                "fen": self._nested(parsed_response, "fen"),
                "confidence": self._nested(parsed_response, "confidence"),
                "warnings": self._nested(parsed_response, "warnings"),
            },
            "duration_ms": duration_ms,
        }
        self._write_private(
            record_dir / "interaction.json",
            json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8"),
        )
        self._enforce_capacity()

    def _enforce_capacity(self) -> None:
        if self.max_total_bytes <= 0 or not self.root.exists():
            return
        directories = sorted(
            (entry for entry in self.root.iterdir() if entry.is_dir()),
            key=lambda entry: entry.stat().st_mtime,
        )
        sizes = {entry: self._directory_size(entry) for entry in directories}
        total = sum(sizes.values())
        for entry in directories:
            if total <= self.max_total_bytes:
                break
            total -= sizes[entry]
            shutil.rmtree(entry)

    @staticmethod
    def _directory_size(path: Path) -> int:
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())

    @staticmethod
    def _write_private(path: Path, content: bytes) -> None:
        path.write_bytes(content)
        if os.name != "nt":
            path.chmod(0o600)

    @staticmethod
    def _image_suffix(content_type: str | None) -> str:
        return {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }.get(content_type or "", ".bin")

    @staticmethod
    def _nested(response: dict[str, Any] | None, key: str) -> Any:
        if response is None:
            return None
        if key in response:
            return response[key]
        detail = response.get("detail")
        return detail.get(key) if isinstance(detail, dict) else None


class InteractionAuditMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        store_getter: Callable[[], InteractionAuditStore | None],
        key_store_getter: Callable[[], APIKeyStore | None],
        require_api_key: bool,
        max_request_bytes: int,
        max_response_bytes: int = 2 * 1024 * 1024,
    ) -> None:
        self.app = app
        self.store_getter = store_getter
        self.key_store_getter = key_store_getter
        self.require_api_key = require_api_key
        self.max_request_bytes = max_request_bytes
        self.max_response_bytes = max_response_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        store = self.store_getter()
        if (
            store is None
            or scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") not in AUDITED_PATHS
        ):
            await self.app(scope, receive, send)
            return

        key_id = self._active_key_id(scope)
        if key_id is None:
            await self.app(scope, receive, send)
            return

        request_body = bytearray()
        request_truncated = False
        response_body = bytearray()
        response_truncated = False
        response_status = 500
        response_headers: list[tuple[bytes, bytes]] = []
        started = perf_counter()

        async def audited_receive() -> Message:
            nonlocal request_truncated
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                remaining = self.max_request_bytes - len(request_body)
                if len(chunk) > remaining:
                    request_body.extend(chunk[: max(remaining, 0)])
                    request_truncated = True
                else:
                    request_body.extend(chunk)
            return message

        async def audited_send(message: Message) -> None:
            nonlocal response_status, response_headers, response_truncated
            if message["type"] == "http.response.start":
                response_status = message["status"]
                response_headers = list(message.get("headers", []))
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                remaining = self.max_response_bytes - len(response_body)
                if len(chunk) > remaining:
                    response_body.extend(chunk[: max(remaining, 0)])
                    response_truncated = True
                else:
                    response_body.extend(chunk)
            await send(message)

        try:
            await self.app(scope, audited_receive, audited_send)
        finally:
            try:
                await store.record(
                    scope=scope,
                    request_body=bytes(request_body),
                    request_truncated=request_truncated,
                    response_status=response_status,
                    response_headers=response_headers,
                    response_body=bytes(response_body),
                    response_truncated=response_truncated,
                    duration_ms=round((perf_counter() - started) * 1000),
                    key_id=key_id,
                )
            except Exception:
                LOGGER.exception("failed to persist interaction audit record")

    def _active_key_id(self, scope: Scope) -> str | None:
        if not self.require_api_key:
            return "authentication-disabled"
        key_store = self.key_store_getter()
        if key_store is None:
            return None
        headers = Headers(scope=scope)
        supplied = headers.get("x-api-key")
        authorization = headers.get("authorization")
        if authorization and authorization.lower().startswith("bearer "):
            supplied = authorization[7:].strip()
        validation = key_store.validate(supplied)
        return validation.key_id if validation.status == "active" else None
