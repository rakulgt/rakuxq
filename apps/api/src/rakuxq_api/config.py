from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    pose_model: str = os.getenv("RAKUXQ_POSE_MODEL", "../../models/pose.onnx")
    layout_model: str = os.getenv("RAKUXQ_LAYOUT_MODEL", "../../models/layout.onnx")
    model_version: str = os.getenv("RAKUXQ_MODEL_VERSION", "cchess-baseline-2025-03-19")
    max_upload_bytes: int = int(os.getenv("RAKUXQ_MAX_UPLOAD_BYTES", str(12 * 1024 * 1024)))
    minimum_board_confidence: float = float(
        os.getenv("RAKUXQ_MIN_BOARD_CONFIDENCE", "0.55")
    )
    minimum_cell_confidence: float = float(
        os.getenv("RAKUXQ_MIN_CELL_CONFIDENCE", "0.75")
    )
    acceptance_confidence: float = float(
        os.getenv("RAKUXQ_ACCEPTANCE_CONFIDENCE", "0.55")
    )
    ort_intra_op_threads: int = int(os.getenv("RAKUXQ_ORT_INTRA_OP_THREADS", "2"))
    portrait_fast_path_ratio: float = float(
        os.getenv("RAKUXQ_PORTRAIT_FAST_PATH_RATIO", "1.5")
    )
    minimum_partial_board_confidence: float = float(
        os.getenv("RAKUXQ_MIN_PARTIAL_BOARD_CONFIDENCE", "0.35")
    )
    minimum_partial_empty_confidence: float = float(
        os.getenv("RAKUXQ_MIN_PARTIAL_EMPTY_CONFIDENCE", "0.35")
    )
    partial_acceptance_confidence: float = float(
        os.getenv("RAKUXQ_PARTIAL_ACCEPTANCE_CONFIDENCE", "0.35")
    )
