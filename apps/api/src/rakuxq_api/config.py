from __future__ import annotations

import os
from dataclasses import dataclass


def _boolean(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
    require_api_key: bool = _boolean("RAKUXQ_REQUIRE_API_KEY")
    api_keys_db: str = os.getenv("RAKUXQ_API_KEYS_DB", "")
    renewal_wechat: str = os.getenv("RAKUXQ_RENEWAL_WECHAT", "lgtqcn")
    renewal_price_cny: int = int(os.getenv("RAKUXQ_RENEWAL_PRICE_CNY", "39"))
    renewal_period_days: int = int(os.getenv("RAKUXQ_RENEWAL_PERIOD_DAYS", "365"))
    audit_dir: str = os.getenv("RAKUXQ_AUDIT_DIR", "")
    audit_retention_hours: int = int(os.getenv("RAKUXQ_AUDIT_RETENTION_HOURS", "12"))
    audit_max_total_bytes: int = int(
        os.getenv("RAKUXQ_AUDIT_MAX_TOTAL_BYTES", str(2 * 1024 * 1024 * 1024))
    )
    public_metrics_db: str = os.getenv("RAKUXQ_PUBLIC_METRICS_DB", "")
    public_event_hours: int = int(os.getenv("RAKUXQ_PUBLIC_EVENT_HOURS", "72"))
    shortcut_url: str = os.getenv("RAKUXQ_SHORTCUT_URL", "")
