from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse

from . import __version__
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

@asynccontextmanager
async def lifespan(_app: FastAPI):
    if provider.ready():
        provider.warmup()
    yield


app = FastAPI(
    title="RakuXQ Vision API",
    version=__version__,
    description="Turn Xiangqi board images into reviewable, engine-ready FEN.",
    lifespan=lifespan,
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
    return {
        "status": "ok" if ready else "degraded",
        "version": __version__,
        "provider": provider.name,
        "provider_ready": ready,
    }


@app.post("/v1/recognitions")
async def recognize(
    image: Annotated[UploadFile, File()],
    side_to_move: Annotated[SideToMove, Form()] = SideToMove.UNKNOWN,
    orientation: Annotated[Orientation, Form()] = Orientation.AUTO,
):
    data = await _read_image(image)
    return asdict(_run(data, side_to_move, orientation))


@app.post("/v1/fen", response_class=PlainTextResponse)
async def fen(
    image: Annotated[UploadFile, File()],
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
