from __future__ import annotations

import hashlib
import hmac
import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from . import __version__
from .api_keys import APIKeyStore, TrialKeyCapacity, TrialKeyCooldown
from .audit import InteractionAuditMiddleware, InteractionAuditStore
from .config import Settings
from .domain import Orientation, RecognitionStatus, SideToMove, parse_side_to_move
from .engines import (
    EngineAnalysisError,
    EngineNotConfigured,
    EngineTimeout,
    InvalidEnginePosition,
    PikafishEngine,
    analysis_to_dict,
)
from .metrics import PublicMetricsStore
from .providers import OnnxRecognitionProvider, ProviderNotReady
from .providers.base import RecognitionFailed
from .service import RecognitionService

settings = Settings()
logger = logging.getLogger(__name__)
provider = OnnxRecognitionProvider(
    pose_model=settings.pose_model,
    layout_model=settings.layout_model,
    model_version=settings.model_version,
    intra_op_num_threads=settings.ort_intra_op_threads,
    portrait_fast_path_ratio=settings.portrait_fast_path_ratio,
)
service = RecognitionService(
    provider=provider,
    minimum_board_confidence=settings.minimum_board_confidence,
    minimum_cell_confidence=settings.minimum_cell_confidence,
    acceptance_confidence=settings.acceptance_confidence,
    minimum_partial_board_confidence=settings.minimum_partial_board_confidence,
    minimum_partial_empty_confidence=settings.minimum_partial_empty_confidence,
    partial_acceptance_confidence=settings.partial_acceptance_confidence,
)
api_key_store = APIKeyStore(settings.api_keys_db) if settings.api_keys_db else None
audit_store = (
    InteractionAuditStore(
        settings.audit_dir,
        settings.audit_retention_hours,
        settings.audit_max_total_bytes,
    )
    if settings.audit_dir
    else None
)
public_metrics_store = (
    PublicMetricsStore(settings.public_metrics_db, settings.public_event_hours)
    if settings.public_metrics_db
    else None
)
analysis_engine = PikafishEngine(
    settings.engine_path,
    settings.engine_network,
    threads=settings.engine_threads,
    hash_mb=settings.engine_hash_mb,
    command_timeout_ms=settings.engine_command_timeout_ms,
    version=settings.engine_version,
)
static_root = Path(__file__).with_name("static")


class AnalysisRequest(BaseModel):
    fen: str
    movetime_ms: int | None = None


def _renewal_detail() -> dict[str, object]:
    return {
        "wechat": settings.renewal_wechat,
        "price_cny": settings.renewal_price_cny,
        "period_days": settings.renewal_period_days,
    }


def _trial_fingerprint(request: Request) -> str:
    if not settings.trial_key_pepper_file:
        raise HTTPException(status_code=503, detail="Temporary keys are unavailable.")
    try:
        pepper = Path(settings.trial_key_pepper_file).read_bytes().strip()
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Temporary keys are unavailable.") from exc
    if len(pepper) < 32:
        raise HTTPException(status_code=503, detail="Temporary keys are unavailable.")
    client_address = request.headers.get("x-real-ip")
    if not client_address:
        client_address = request.client.host if request.client else "unknown"
    return hmac.new(pepper, client_address.encode("utf-8"), hashlib.sha256).hexdigest()


def require_api_key(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> None:
    if not settings.require_api_key:
        return
    if api_key_store is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "API_KEY_STORE_UNAVAILABLE", "message": "Authentication unavailable."},
        )
    supplied = x_api_key
    if authorization and authorization.lower().startswith("bearer "):
        supplied = authorization[7:].strip()
    validation = api_key_store.validate(supplied)
    if validation.status == "active":
        return
    if validation.status == "expired":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "API_KEY_EXPIRED",
                "message": (
                    f"API key expired. Contact WeChat {settings.renewal_wechat} to renew."
                ),
                "renewal": _renewal_detail(),
            },
        )
    if validation.status == "revoked":
        raise HTTPException(
            status_code=403,
            detail={"code": "API_KEY_REVOKED", "message": "API key revoked."},
        )
    if validation.status == "store_unavailable":
        raise HTTPException(
            status_code=503,
            detail={"code": "API_KEY_STORE_UNAVAILABLE", "message": "Authentication unavailable."},
        )
    raise HTTPException(
        status_code=401,
        detail={
            "code": "API_KEY_REQUIRED" if validation.status == "missing" else "API_KEY_INVALID",
            "message": "Provide a valid API key in Authorization: Bearer or X-API-Key.",
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.require_api_key and api_key_store is not None:
        api_key_store.initialize()
    if provider.ready():
        provider.warmup()
    if audit_store is not None:
        audit_store.prune()
    if public_metrics_store is not None:
        public_metrics_store.initialize()
        if settings.audit_dir:
            public_metrics_store.import_audit_directory(settings.audit_dir)
    if analysis_engine.configured:
        try:
            analysis_engine.start()
        except EngineAnalysisError:
            logger.exception("Pikafish engine startup failed; vision endpoints remain available")
    try:
        yield
    finally:
        analysis_engine.close()


app = FastAPI(
    title="RakuXQ Vision API",
    version=__version__,
    description="Turn Xiangqi board images into reviewable, engine-ready FEN.",
    lifespan=lifespan,
)
app.add_middleware(
    InteractionAuditMiddleware,
    store_getter=lambda: audit_store,
    key_store_getter=lambda: api_key_store,
    require_api_key=settings.require_api_key,
    max_request_bytes=settings.max_upload_bytes + 1024 * 1024,
)
app.mount("/static", StaticFiles(directory=static_root), name="static")


async def _read_image(image: UploadFile) -> bytes:
    allowed = {"image/jpeg", "image/png", "image/webp"}
    if image.content_type not in allowed:
        raise HTTPException(status_code=415, detail="unsupported image content type")
    data = await image.read(settings.max_upload_bytes + 1)
    if not data:
        raise HTTPException(status_code=400, detail="empty image")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="image exceeds upload limit")
    return data


def _run(data: bytes, side_to_move: SideToMove, orientation: Orientation):
    try:
        result = service.recognize(data, side_to_move, orientation)
        if public_metrics_store is not None:
            public_metrics_store.record(result)
        return result
    except ProviderNotReady as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RecognitionFailed as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _normalize_side_to_move(value: str) -> SideToMove:
    try:
        return parse_side_to_move(value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _analysis_time(requested: int | None) -> int:
    value = settings.engine_default_movetime_ms if requested is None else requested
    if value < 50 or value > settings.engine_max_movetime_ms:
        raise HTTPException(
            status_code=422,
            detail=(
                "movetime_ms must be between 50 and "
                f"{settings.engine_max_movetime_ms} milliseconds"
            ),
        )
    return value


def _run_analysis(fen_value: str, movetime_ms: int | None):
    try:
        return analysis_engine.analyze(fen_value, _analysis_time(movetime_ms))
    except InvalidEnginePosition as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_XIANGQI_FEN", "message": str(exc)},
        ) from exc
    except EngineNotConfigured as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "ENGINE_NOT_CONFIGURED", "message": str(exc)},
        ) from exc
    except EngineTimeout as exc:
        raise HTTPException(
            status_code=504,
            detail={"code": "ENGINE_TIMEOUT", "message": str(exc)},
        ) from exc
    except EngineAnalysisError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "ENGINE_ANALYSIS_FAILED", "message": str(exc)},
        ) from exc


@app.get("/healthz")
def healthz():
    ready = provider.ready()
    authentication_ready = not settings.require_api_key or (
        api_key_store is not None and api_key_store.ready()
    )
    return {
        "status": "ok" if ready and authentication_ready else "degraded",
        "version": __version__,
        "provider": provider.name,
        "provider_ready": ready,
        "authentication_required": settings.require_api_key,
        "authentication_ready": authentication_ready,
        "engine_configured": analysis_engine.configured,
        "engine_ready": analysis_engine.ready,
        "engine": asdict(analysis_engine.identity) if analysis_engine.identity else None,
    }


@app.get("/", include_in_schema=False)
def homepage() -> FileResponse:
    return FileResponse(static_root / "index.html", media_type="text/html")


@app.get("/lab", include_in_schema=False)
@app.get("/lab/", include_in_schema=False)
def position_lab() -> FileResponse:
    return FileResponse(static_root / "lab.html", media_type="text/html")


@app.get("/fen/{fen_value:path}", include_in_schema=False)
def fen_position(fen_value: str) -> FileResponse:
    # Validation is intentionally performed by the lab UI so malformed shared links
    # receive a useful, interactive error instead of an opaque web-server 404.
    del fen_value
    return FileResponse(static_root / "lab.html", media_type="text/html")


@app.get("/developers", include_in_schema=False)
def developer_guide() -> FileResponse:
    return FileResponse(static_root / "developers.html", media_type="text/html")


@app.get("/api/public/stats", include_in_schema=False)
def public_stats() -> JSONResponse:
    if public_metrics_store is None:
        snapshot: dict[str, object] = {
            "generated_at": datetime.now(UTC).isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            ),
            "recent_window_hours": settings.public_event_hours,
            "lifetime": {
                "successful": 0,
                "accepted": 0,
                "review_required": 0,
                "acceptance_rate": 0.0,
                "first_seen_at": None,
                "last_seen_at": None,
            },
            "recent": {
                "successful": 0,
                "accepted": 0,
                "review_required": 0,
                "acceptance_rate": 0.0,
                "average_duration_ms": 0,
            },
            "hourly": [],
            "events": [],
        }
    else:
        snapshot = public_metrics_store.snapshot()
    shortcut_url = settings.shortcut_url.strip()
    snapshot["shortcut_url"] = (
        shortcut_url
        if shortcut_url.startswith("https://www.icloud.com/shortcuts/")
        else None
    )
    return JSONResponse(snapshot, headers={"Cache-Control": "public, max-age=5"})


@app.post("/api/public/trial-keys", include_in_schema=False)
def issue_trial_key(request: Request) -> JSONResponse:
    if api_key_store is None:
        raise HTTPException(status_code=503, detail="Temporary keys are unavailable.")
    try:
        plaintext, expires_at = api_key_store.issue_trial(
            _trial_fingerprint(request),
            minutes=settings.trial_key_minutes,
            active_limit=settings.trial_key_active_limit,
        )
    except TrialKeyCooldown as exc:
        raise HTTPException(
            status_code=429,
            detail={
                "code": "TRIAL_KEY_ALREADY_ACTIVE",
                "message": "A temporary key was already issued to this client.",
                "retry_after_seconds": exc.retry_after_seconds,
            },
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except TrialKeyCapacity as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "TRIAL_KEY_CAPACITY_REACHED", "message": "Please try again later."},
        ) from exc
    return JSONResponse(
        {
            "api_key": plaintext,
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
            "expires_in_seconds": settings.trial_key_minutes * 60,
            "authorization": f"Bearer {plaintext}",
            "notice": "Shown once. Test uploads follow the 12-hour quality-audit policy.",
        },
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "Referrer-Policy": "no-referrer",
        },
    )


@app.post("/v1/recognitions")
async def recognize(
    image: Annotated[UploadFile, File()],
    _api_key: Annotated[None, Depends(require_api_key)],
    side_to_move: Annotated[str, Form()] = SideToMove.UNKNOWN.value,
    orientation: Annotated[Orientation, Form()] = Orientation.AUTO,
):
    data = await _read_image(image)
    return asdict(_run(data, _normalize_side_to_move(side_to_move), orientation))


@app.post("/v1/analyses")
def analyze_position(
    payload: AnalysisRequest,
    _api_key: Annotated[None, Depends(require_api_key)],
):
    return analysis_to_dict(_run_analysis(payload.fen, payload.movetime_ms))


@app.post("/v1/solve")
async def solve(
    image: Annotated[UploadFile, File()],
    _api_key: Annotated[None, Depends(require_api_key)],
    side_to_move: Annotated[str, Form()] = SideToMove.UNKNOWN.value,
    orientation: Annotated[Orientation, Form()] = Orientation.AUTO,
    movetime_ms: Annotated[int | None, Form()] = None,
):
    data = await _read_image(image)
    recognition = _run(data, _normalize_side_to_move(side_to_move), orientation)
    recognition_payload = asdict(recognition)
    if recognition.status != RecognitionStatus.ACCEPTED or recognition.full_fen is None:
        return {
            "status": recognition.status,
            "fen": recognition.fen,
            "recognition": recognition_payload,
            "analysis": None,
        }
    analysis = await run_in_threadpool(
        _run_analysis,
        recognition.full_fen,
        movetime_ms,
    )
    return {
        "status": recognition.status,
        "fen": recognition.fen,
        "recognition": recognition_payload,
        "analysis": analysis_to_dict(analysis),
    }


@app.post("/v1/fen", response_class=PlainTextResponse)
async def fen(
    image: Annotated[UploadFile, File()],
    _api_key: Annotated[None, Depends(require_api_key)],
    side_to_move: Annotated[str, Form()] = SideToMove.UNKNOWN.value,
    orientation: Annotated[Orientation, Form()] = Orientation.AUTO,
):
    data = await _read_image(image)
    result = _run(data, _normalize_side_to_move(side_to_move), orientation)
    if result.status != RecognitionStatus.ACCEPTED or result.fen is None:
        raise HTTPException(
            status_code=422,
            detail={
                "request_id": result.request_id,
                "status": result.status,
                "piece_placement": result.piece_placement,
                "warnings": result.warnings,
            },
        )
    prediction = result.prediction
    return PlainTextResponse(
        result.fen,
        headers={
            "X-RakuXQ-Request-Id": result.request_id,
            "X-RakuXQ-Provider": prediction.provider if prediction else "none",
            "X-RakuXQ-Model-Version": prediction.model_version if prediction else "none",
            "X-RakuXQ-Warnings": ",".join(result.warnings) or "none",
            "X-RakuXQ-Assumed-Empty-Cells": ";".join(
                f"{cell.rank},{cell.file}" for cell in result.assumed_empty_cells
            )
            or "none",
            "X-RakuXQ-Assumed-Empty-Details": ";".join(
                f"{cell.rank},{cell.file}:{cell.reason}"
                for cell in result.assumed_empty_cells
            )
            or "none",
        },
    )
