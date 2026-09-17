from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse

from . import __version__
from .api_keys import APIKeyStore
from .audit import InteractionAuditMiddleware, InteractionAuditStore
from .config import Settings
from .domain import Orientation, RecognitionStatus, SideToMove
from .providers import OnnxRecognitionProvider, ProviderNotReady
from .providers.base import RecognitionFailed
from .service import RecognitionService

settings = Settings()
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


def _renewal_detail() -> dict[str, object]:
    return {
        "wechat": settings.renewal_wechat,
        "price_cny": settings.renewal_price_cny,
        "period_days": settings.renewal_period_days,
    }


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
    yield


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
        return service.recognize(data, side_to_move, orientation)
    except ProviderNotReady as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RecognitionFailed as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
    }


@app.post("/v1/recognitions")
async def recognize(
    image: Annotated[UploadFile, File()],
    _api_key: Annotated[None, Depends(require_api_key)],
    side_to_move: Annotated[SideToMove, Form()] = SideToMove.UNKNOWN,
    orientation: Annotated[Orientation, Form()] = Orientation.AUTO,
):
    data = await _read_image(image)
    return asdict(_run(data, side_to_move, orientation))


@app.post("/v1/fen", response_class=PlainTextResponse)
async def fen(
    image: Annotated[UploadFile, File()],
    _api_key: Annotated[None, Depends(require_api_key)],
    side_to_move: Annotated[SideToMove, Form()] = SideToMove.UNKNOWN,
    orientation: Annotated[Orientation, Form()] = Orientation.AUTO,
):
    data = await _read_image(image)
    result = _run(data, side_to_move, orientation)
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
